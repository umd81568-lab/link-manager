import argparse
import json
import os
import sys

import paramiko

from deploy_config import add_ssh_target_args, connect_ssh_from_args, resolve_ssh_target

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_LINK_SCRIPT = os.path.join(BASE_DIR, "link_manager_local.py")
REMOTE_LINK_SCRIPT = "/opt/links/link_manager.py"


class DeployError(Exception):
    def __init__(self, code, message, hint=None, **details):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.details = details



def emit_json(payload):
    print(json.dumps(payload))



def emit_error(code, message, hint=None, **details):
    payload = {"error": code, "message": message}
    if hint:
        payload["hint"] = hint
    payload.update(details)
    emit_json(payload)
    return 1



def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Deploy link-manager updates over SSH.",
    )
    parser.add_argument("password", nargs="?", help="SSH password (optional when using --key-file)")
    parser.add_argument("domain", nargs="?", default="")
    parser.add_argument("email", nargs="?", default="")
    parser.add_argument("port", nargs="?", type=int, default=5002)
    add_ssh_target_args(parser)
    return parser.parse_args(argv)



def run(client, cmd):
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode(errors="ignore")
    err = stderr.read().decode(errors="ignore")
    exit_status = stdout.channel.recv_exit_status()
    return exit_status, out, err



def require_local_file(path):
    if not os.path.isfile(path):
        raise DeployError(
            "missing_local_file",
            f"Required local file not found: {path}",
            hint="Run this script from the repository checkout and ensure link_manager_local.py exists.",
            path=path,
        )



def run_step(client, cmd, step, critical=False, expected_stdout=None):
    exit_status, out, err = run(client, cmd)
    if out:
        print(out)
    if err:
        print(err)
    if critical and exit_status != 0:
        raise DeployError(
            "remote_command_failed",
            f"Remote step failed: {step}",
            hint="Review the command output above and fix the remote service/package issue before retrying.",
            step=step,
            command=cmd,
            exit_status=exit_status,
        )
    if expected_stdout is not None and out.strip() != expected_stdout:
        raise DeployError(
            "remote_state_unexpected",
            f"Remote step returned unexpected output: {step}",
            hint=f"Expected '{expected_stdout}' but received '{out.strip()}'. Review the remote service state.",
            step=step,
            command=cmd,
            exit_status=exit_status,
            stdout=out.strip(),
        )
    return out, err, exit_status



def main(argv=None):
    target_host = None
    try:
        args = parse_args(argv)
        target_host = resolve_ssh_target(args)["host"]
        require_local_file(LOCAL_LINK_SCRIPT)
        client, settings = connect_ssh_from_args(args, prompt="Enter Server Root Password: ", timeout=20)
    except DeployError as exc:
        return emit_error(exc.code, exc.message, exc.hint, **exc.details)
    except paramiko.AuthenticationException:
        return emit_error(
            "ssh_auth_failed",
            "SSH authentication failed.",
            hint="Verify the SSH password or provide a valid key with --key-file / DEPLOY_KEY_FILE.",
        )
    except (paramiko.SSHException, OSError, ValueError) as exc:
        return emit_error(
            "ssh_connect_failed",
            f"Unable to connect to {target_host or 'target host'}.",
            hint="Check --host/DEPLOY_HOST, SSH port, firewall rules, and whether the server is reachable.",
            detail=str(exc),
        )

    host = settings["host"]
    port = args.port
    domain = args.domain
    email = args.email

    try:
        sftp = client.open_sftp()
        try:
            sftp.put(LOCAL_LINK_SCRIPT, REMOTE_LINK_SCRIPT)
        finally:
            sftp.close()

        cmds_common = [
            ("install requests", "/opt/links/venv/bin/pip install --no-cache-dir requests", True, None),
            ("enable safe mode", "bash -lc 'grep -q ^LINK_SAFE_MODE= /etc/links.env && sed -i \"s/^LINK_SAFE_MODE=.*/LINK_SAFE_MODE=1/\" /etc/links.env || echo LINK_SAFE_MODE=1 >> /etc/links.env'", True, None),
            ("set allowed hosts", "bash -lc 'grep -q ^LINK_ALLOWED_HOSTS= /etc/links.env && sed -i \"s/^LINK_ALLOWED_HOSTS=.*/LINK_ALLOWED_HOSTS=example.com,pcc.police.gov.bd/\" /etc/links.env || echo LINK_ALLOWED_HOSTS=example.com,pcc.police.gov.bd >> /etc/links.env'", True, None),
            ("set blocked patterns", "bash -lc 'grep -q ^LINK_BLOCK_PATTERNS= /etc/links.env && sed -i \"s/^LINK_BLOCK_PATTERNS=.*/LINK_BLOCK_PATTERNS=adult,porn/\" /etc/links.env || echo LINK_BLOCK_PATTERNS=adult,porn >> /etc/links.env'", True, None),
            ("reload systemd", "systemctl daemon-reload", True, None),
            ("restart links", "systemctl restart links", True, None),
            ("verify links service", "systemctl is-active links", True, "active"),
            ("open firewall port", "bash -lc 'which ufw >/dev/null 2>&1 && ufw allow 80 && ufw allow 443 && ufw allow %d/tcp || true'" % port, False, None),
        ]
        for step, cmd, critical, expected_stdout in cmds_common:
            run_step(client, cmd, step, critical=critical, expected_stdout=expected_stdout)

        out, _, _ = run_step(
            client,
            "bash -lc 'systemctl list-unit-files | grep -q ^caddy.service && echo caddy_present || echo caddy_absent'",
            "detect caddy",
            critical=True,
        )
        caddy_present = out.strip() == "caddy_present"

        if not caddy_present:
            run_step(
                client,
                "bash -lc 'apt-get update -y && apt-get install -y nginx'",
                "install nginx",
                critical=True,
            )
            conf = (
                "server {\n"
                + "    listen 80 default_server;\n"
                + "    server_name %s;\n" % (domain if domain else "_")
                + "    location / {\n"
                + "        proxy_pass http://127.0.0.1:%d;\n" % port
                + "        proxy_set_header Host $host;\n"
                + "        proxy_set_header X-Real-IP $remote_addr;\n"
                + "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
                + "        proxy_set_header X-Forwarded-Proto $scheme;\n"
                + "    }\n"
                + "}\n"
            )
            sftp = client.open_sftp()
            try:
                with sftp.open("/etc/nginx/sites-available/links.conf", "w") as handle:
                    handle.write(conf)
            finally:
                sftp.close()

            for step, cmd, critical, expected_stdout in [
                ("enable nginx site", "bash -lc 'ln -sf /etc/nginx/sites-available/links.conf /etc/nginx/sites-enabled/links.conf'", True, None),
                ("remove default nginx site", "bash -lc 'test -e /etc/nginx/sites-enabled/default && rm -f /etc/nginx/sites-enabled/default || true'", False, None),
                ("test nginx config", "bash -lc 'nginx -t'", True, None),
                ("reload nginx", "systemctl reload nginx", True, None),
                ("verify nginx service", "systemctl is-active nginx", True, "active"),
            ]:
                run_step(client, cmd, step, critical=critical, expected_stdout=expected_stdout)

        if caddy_present:
            for step, cmd, critical in [
                (
                    "ensure caddy ord redirect",
                    "bash -lc 'if [ -f /etc/caddy/Caddyfile ]; then grep -q \"redir /ord*\" /etc/caddy/Caddyfile || sed -i \"/^:80 {/a \\\tredir /ord* /ords{path}\" /etc/caddy/Caddyfile; fi'",
                    True,
                ),
                ("reload caddy", "bash -lc 'systemctl reload caddy'", True),
            ]:
                run_step(client, cmd, step, critical=critical)

        for step, cmd in [
            ("links health", "bash -lc 'curl -sS http://127.0.0.1:%d/health || true'" % port),
            ("links redirect test", "bash -lc 'curl -sS http://127.0.0.1:%d/r/test || true'" % port),
            ("localhost health", "bash -lc 'curl -sS http://127.0.0.1/health || true'"),
            ("check port 80", 'bash -lc "ss -ltnp | grep \":80\" || true"'),
        ]:
            run_step(client, cmd, step)

        for step, cmd in [
            ("start ords", "bash -lc 'cd /opt/ords && nohup ./bin/ords --config /opt/ords/config serve --port 8080 > /var/log/ords.log 2>&1 & disown'"),
            ("verify ords listener", 'bash -lc "sleep 3; ss -ltnp | grep \'127.0.0.1:8080\' || ss -ltnp | grep \'8080\' || tail -n 50 /var/log/ords.log || true"'),
            ("reload caddy after ords", "bash -lc 'systemctl list-unit-files | grep -q ^caddy.service && systemctl reload caddy || true'"),
            ("ords health", "bash -lc 'curl -sS -I http://127.0.0.1:8080/ords/ | head -n 1 || true'"),
        ]:
            run_step(client, cmd, step, critical=(step == "start ords"))

        if caddy_present:
            out, _, _ = run_step(
                client,
                "bash -lc 'ss -tlnp | grep -q :8080 && echo ords_up || echo ords_down'",
                "detect ords state",
                critical=True,
            )
            if out.strip() == "ords_down":
                for step, cmd in [
                    (
                        "configure caddy ords fallback",
                        "bash -lc 'if [ -f /etc/caddy/Caddyfile ]; then sed -i \"/^:80 {$/a \\\thandle /ords/* {\\n        reverse_proxy https://pcc.police.gov.bd {\\n             header_up Host pcc.police.gov.bd\\n             header_up X-Real-IP {remote}\\n             header_up X-Forwarded-For {remote}\\n             header_up X-Forwarded-Proto {scheme}\\n        }\\n    }\" /etc/caddy/Caddyfile; fi'",
                    ),
                    ("reload caddy fallback", "bash -lc 'systemctl reload caddy'"),
                ]:
                    run_step(client, cmd, step, critical=True)

        if domain and email:
            run_step(
                client,
                f"bash -lc 'apt-get install -y certbot python3-certbot-nginx && certbot --nginx -d {domain} -m {email} --agree-tos -n --redirect'",
                "request certbot certificate",
                critical=True,
            )
            run_step(client, "systemctl reload nginx", "reload nginx after certbot", critical=True)

        result = {
            "host": host,
            "ip_url": f"http://{host}/r/demo",
            "ip_port_url": f"http://{host}:{port}/r/demo",
        }
        if domain:
            result["domain_url"] = f"http://{domain}/r/demo"
            result["domain_https_url"] = f"https://{domain}/r/demo"
        emit_json(result)
        return 0
    except (paramiko.SSHException, OSError) as exc:
        return emit_error(
            "sftp_or_ssh_error",
            "SSH/SFTP operation failed during deployment.",
            hint="Verify the remote path permissions and that the target services/directories already exist on the server.",
            detail=str(exc),
        )
    except DeployError as exc:
        return emit_error(exc.code, exc.message, exc.hint, **exc.details)
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
