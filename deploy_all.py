import sys
import json
import paramiko

HOST = "207.180.249.220"
USER = "root"

def run(client, cmd):
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode(errors="ignore")
    err = stderr.read().decode(errors="ignore")
    return out, err

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error":"usage","hint":"python deploy_all.py <root_password> [domain] [email] [port=5002]"}))
        return 1
    pwd = sys.argv[1]
    domain = sys.argv[2] if len(sys.argv) > 2 else ""
    email = sys.argv[3] if len(sys.argv) > 3 else ""
    port = int(sys.argv[4]) if len(sys.argv) > 4 else 5002

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=pwd)

    sftp = client.open_sftp()
    sftp.put("link_manager_local.py", "/opt/links/link_manager.py")
    sftp.close()

    cmds_common = [
        "/opt/links/venv/bin/pip install --no-cache-dir requests",
        "bash -lc 'grep -q ^LINK_SAFE_MODE= /etc/links.env && sed -i \"s/^LINK_SAFE_MODE=.*/LINK_SAFE_MODE=1/\" /etc/links.env || echo LINK_SAFE_MODE=1 >> /etc/links.env'",
        "bash -lc 'grep -q ^LINK_ALLOWED_HOSTS= /etc/links.env && sed -i \"s/^LINK_ALLOWED_HOSTS=.*/LINK_ALLOWED_HOSTS=example.com,pcc.police.gov.bd/\" /etc/links.env || echo LINK_ALLOWED_HOSTS=example.com,pcc.police.gov.bd >> /etc/links.env'",
        "bash -lc 'grep -q ^LINK_BLOCK_PATTERNS= /etc/links.env && sed -i \"s/^LINK_BLOCK_PATTERNS=.*/LINK_BLOCK_PATTERNS=adult,porn/\" /etc/links.env || echo LINK_BLOCK_PATTERNS=adult,porn >> /etc/links.env'",
        "systemctl daemon-reload",
        "systemctl restart links",
        "systemctl is-active links",
        "bash -lc 'which ufw >/dev/null 2>&1 && ufw allow 80 && ufw allow 443 && ufw allow %d/tcp || true'" % port,
    ]
    for c in cmds_common:
        out, err = run(client, c)
        print(out or err)

    # Detect Caddy presence, decide whether to configure Nginx
    out, err = run(client, "bash -lc 'systemctl list-unit-files | grep -q ^caddy.service && echo caddy_present || echo caddy_absent'")
    caddy_present = (out.strip() == "caddy_present")

    if not caddy_present:
        out, err = run(client, "bash -lc 'apt-get update -y && apt-get install -y nginx'")
        print(out or err)
        conf = (
            "server {\n"+
            "    listen 80 default_server;\n"+
            "    server_name %s;\n" % (domain if domain else "_")+
            "    location / {\n"+
            "        proxy_pass http://127.0.0.1:%d;\n" % port+
            "        proxy_set_header Host $host;\n"+
            "        proxy_set_header X-Real-IP $remote_addr;\n"+
            "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"+
            "        proxy_set_header X-Forwarded-Proto $scheme;\n"+
            "    }\n"+
            "}\n"
        )
        sftp = client.open_sftp()
        with sftp.open(f"/etc/nginx/sites-available/links.conf", "w") as f:
            f.write(conf)
        sftp.close()

        for c in [
            "bash -lc 'ln -sf /etc/nginx/sites-available/links.conf /etc/nginx/sites-enabled/links.conf'",
            "bash -lc 'test -e /etc/nginx/sites-enabled/default && rm -f /etc/nginx/sites-enabled/default || true'",
            "bash -lc 'nginx -t'",
            "systemctl reload nginx",
            "systemctl is-active nginx"
        ]:
            out, err = run(client, c)
            print(out or err)

    # Ensure /ord alias redirects to /ords in Caddy (if installed)
    if caddy_present:
        for c in [
            "bash -lc 'if [ -f /etc/caddy/Caddyfile ]; then grep -q " + "\"redir /ord*\"" + " /etc/caddy/Caddyfile || sed -i \"/^:80 {/a \\tredir /ord* /ords{path}\" /etc/caddy/Caddyfile; fi'",
            "bash -lc 'systemctl reload caddy'",
        ]:
            out, err = run(client, c)
            print(out or err)

    # Basic health checks (prints outputs for verification)
    for c in [
        "bash -lc 'curl -sS http://127.0.0.1:%d/health || true'" % port,
        "bash -lc 'curl -sS http://127.0.0.1:%d/r/test || true'" % port,
        "bash -lc 'curl -sS http://127.0.0.1/health || true'",
        "bash -lc \"ss -ltnp | grep ':80' || true\"",
    ]:
        out, err = run(client, c)
        print(out or err)

    # Start ORDS backend on 8080 and verify
    for c in [
        "bash -lc 'cd /opt/ords && nohup ./bin/ords --config /opt/ords/config serve --port 8080 > /var/log/ords.log 2>&1 & disown || true'",
        'bash -lc "sleep 3; ss -ltnp | grep \'128.0.0.1:8080\' || ss -ltnp | grep \'8080\' || tail -n 50 /var/log/ords.log || true"',
        "bash -lc 'systemctl list-unit-files | grep -q ^caddy.service && systemctl reload caddy || true'",
        "bash -lc 'curl -sS -I http://127.0.0.1:8080/ords/ | head -n 1 || true'",
    ]:
        out, err = run(client, c)
        print(out or err)

    # If Caddy is present and ORDS is not listening, configure fallback proxy to PCC
    if caddy_present:
        out, err = run(client, "bash -lc 'ss -tlnp | grep -q :8080 && echo ords_up || echo ords_down'")
        print(out or err)
        if (out.strip() == "ords_down"):
            cmds = [
                "bash -lc 'if [ -f /etc/caddy/Caddyfile ]; then sed -i \"/^:80 {$/a \\thandle \/ords\/* {\\n        reverse_proxy https:\/\/pcc.police.gov.bd {\\n             header_up Host pcc.police.gov.bd\\n             header_up X-Real-IP {remote}\\n             header_up X-Forwarded-For {remote}\\n             header_up X-Forwarded-Proto {scheme}\\n        }\\n    }\" /etc/caddy/Caddyfile; fi'",
                "bash -lc 'systemctl reload caddy'",
            ]
            for c in cmds:
                o, e = run(client, c)
                print(o or e)

    if domain and email:
        out, err = run(client, f"bash -lc 'apt-get install -y certbot python3-certbot-nginx && certbot --nginx -d {domain} -m {email} --agree-tos -n --redirect'"
        )
        print(out or err)
        out, err = run(client, "systemctl reload nginx")
        print(out or err)

    client.close()
    result = {"ip_url": f"http://{HOST}/r/demo", "ip_port_url": f"http://{HOST}:{port}/r/demo"}
    if domain:
        result["domain_url"] = f"http://{domain}/r/demo"
        result["domain_https_url"] = f"https://{domain}/r/demo"
    print(json.dumps(result))
    return 0

if __name__ == "__main__":
    sys.exit(main())
