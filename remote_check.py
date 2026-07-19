import argparse
import sys

from deploy_config import add_ssh_target_args, connect_ssh_from_args



def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run remote deployment diagnostics.")
    parser.add_argument("password", nargs="?", help="SSH password (optional when using --key-file)")
    add_ssh_target_args(parser)
    return parser.parse_args(argv)



def run(client, cmd):
    print(f"$ {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode(errors="ignore")
    err = stderr.read().decode(errors="ignore")
    if out:
        print(out.strip())
    if err:
        print(err.strip())



def main(argv=None):
    args = parse_args(argv)
    try:
        client, _ = connect_ssh_from_args(args, prompt="Enter Server Root Password: ")
    except Exception as exc:
        print(f"SSH connection failed: {exc}")
        return 1

    try:
        cmds = [
            "systemctl is-active caddy || echo caddy_inactive",
            "ss -tlnp | grep ':80' || echo no_port80",
            "ls -l /var/www/dashboard/index.html || echo missing_index",
            "curl -s -o /dev/null -w '%{http_code}\\n' http://127.0.0.1/ || echo curl_fail",
            "curl -s -o /dev/null -w '%{http_code}\\n' http://127.0.0.1/ords || echo curl_fail_ords",
            "ss -tlnp | grep ':8080' || echo no_port8080",
            "tail -n 100 /var/log/ords.log || echo no_ords_log",
            "docker ps -a --filter name=oracle-db --format '{{.Status}} {{.Names}}' || true",
            "docker logs --tail 50 oracle-db || true",
            "pgrep -a ords || echo ords_not_running",
            "tail -n 50 /root/server_setup.log || true",
        ]
        for cmd in cmds:
            run(client, cmd)
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
