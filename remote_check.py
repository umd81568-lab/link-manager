import paramiko
import sys

HOST = "207.180.249.220"
USER = "root"

def run(client, cmd):
    print(f"$ {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode(errors='ignore')
    err = stderr.read().decode(errors='ignore')
    if out:
        print(out.strip())
    if err:
        print(err.strip())

def main():
    if len(sys.argv) < 2:
        print("Usage: python remote_check.py <root_password>")
        sys.exit(1)
    pwd = sys.argv[1]
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=pwd)

    cmds = [
        "systemctl is-active caddy || echo caddy_inactive",
        "ss -tlnp | grep ':80' || echo no_port80",
        "ls -l /var/www/dashboard/index.html || echo missing_index",
        "curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1/ || echo curl_fail",
        "curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1/ords || echo curl_fail_ords",
        "ss -tlnp | grep ':8080' || echo no_port8080",
        "tail -n 100 /var/log/ords.log || echo no_ords_log",
        "docker ps -a --filter name=oracle-db --format '{{.Status}} {{.Names}}' || true",
        "docker logs --tail 50 oracle-db || true",
        "pgrep -a ords || echo ords_not_running",
        "tail -n 50 /root/server_setup.log || true",
    ]
    for cmd in cmds:
        run(c, cmd)
    c.close()

if __name__ == "__main__":
    main()
