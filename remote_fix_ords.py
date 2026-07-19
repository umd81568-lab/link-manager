import argparse
import sys

from deploy_config import add_ssh_target_args, connect_ssh_from_args



def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Repair and restart the remote ORDS service.")
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


def run_with_input(client, cmd, lines):
    print(f"$ {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd)
    for line in lines:
        stdin.write(f"{line}\n")
    stdin.flush()
    stdin.channel.shutdown_write()
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
        cmd_get_db = "awk -F': ' '/Admin Password/ {print $2}' /root/server_setup.log | tail -n 1"
        stdin, stdout, stderr = client.exec_command(cmd_get_db)
        db_password = (stdout.read().decode() or "").strip()
        if not db_password:
            print("Could not retrieve DB password from log.")
            return 2
        print("Retrieved ORDS database password from setup log.")

        run(client, "mkdir -p /opt/ords/config /var/log/ords")
        install_cmd = (
            "/opt/ords/bin/ords --config /opt/ords/config install "
            "--log-folder /var/log/ords --admin-user SYS --db-hostname localhost "
            "--db-port 1521 --db-servicename XE --feature-sdw true"
        )
        run_with_input(client, install_cmd, [db_password, db_password])
        run(client, "nohup /opt/ords/bin/ords --config /opt/ords/config serve --port 8080 > /var/log/ords.log 2>&1 &")
        run(client, "sleep 3; ss -tlnp | grep ':8080' || echo no_port8080")
        run(client, "curl -s -o /dev/null -w '%{http_code}\\n' http://127.0.0.1:8080/ords/ || echo curl_fail_ords")
        run(client, "pgrep -a ords || echo ords_not_running")
        run(client, "tail -n 200 /var/log/ords.log || echo no_ords_log")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
