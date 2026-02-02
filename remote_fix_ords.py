import paramiko
import sys

HOST = "207.180.249.220"
USER = "root"

def run(c, cmd):
    print(f"$ {cmd}")
    stdin, stdout, stderr = c.exec_command(cmd)
    out = stdout.read().decode(errors='ignore')
    err = stderr.read().decode(errors='ignore')
    if out:
        print(out.strip())
    if err:
        print(err.strip())

def main():
    if len(sys.argv) < 2:
        print("Usage: python remote_fix_ords.py <root_password>")
        sys.exit(1)
    pwd = sys.argv[1]
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=pwd)

    # Extract DB password from setup log
    cmd_get_db = "awk -F': ' '/Admin Password/ {print $2}' /root/server_setup.log | tail -n 1"
    stdin, stdout, stderr = c.exec_command(cmd_get_db)
    DB_PASSWORD = (stdout.read().decode() or '').strip()
    if not DB_PASSWORD:
        print("Could not retrieve DB password from log.")
        c.close(); sys.exit(2)
    print(f"DB_PASSWORD: {DB_PASSWORD}")

    # Ensure ords dirs
    run(c, "mkdir -p /opt/ords/config /var/log/ords")

    # Re-run ORDS install now that DB is ready
    install_cmd = (
        "bash -lc \"printf '%s\\n%s\\n' '" + DB_PASSWORD + "' '" + DB_PASSWORD + "' | "
        "/opt/ords/bin/ords --config /opt/ords/config install "
        "--log-folder /var/log/ords --admin-user SYS --db-hostname localhost "
        "--db-port 1521 --db-servicename XE --feature-sdw true\""
    )
    run(c, install_cmd)

    # Start ORDS
    run(c, "nohup /opt/ords/bin/ords --config /opt/ords/config serve --port 8080 > /var/log/ords.log 2>&1 &")

    # Verify
    run(c, "sleep 3; ss -tlnp | grep ':8080' || echo no_port8080")
    run(c, "curl -s -o /dev/null -w '%{http_code}\\n' http://127.0.0.1:8080/ords/ || echo curl_fail_ords")
    run(c, "pgrep -a ords || echo ords_not_running")
    run(c, "tail -n 200 /var/log/ords.log || echo no_ords_log")
    c.close()

if __name__ == "__main__":
    main()
