import argparse
import sys

from deploy_config import add_ssh_target_args, connect_ssh_from_args



def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Check whether setup_server.sh is still running on the server.")
    parser.add_argument("password", nargs="?", help="SSH password (optional when using --key-file)")
    add_ssh_target_args(parser)
    return parser.parse_args(argv)



def check_status(argv=None):
    args = parse_args(argv)
    try:
        client, settings = connect_ssh_from_args(args, prompt="Enter Server Root Password: ")
    except Exception as exc:
        print(f"Error: {exc}")
        return 1

    try:
        print(f"Connecting to {settings['host']}...")
        print("Connected.")

        stdin, stdout, stderr = client.exec_command("ps aux | grep setup_server.sh | grep -v grep")
        running = stdout.read().decode().strip()
        if running:
            print("STATUS: Setup is RUNNING.")
        else:
            print("STATUS: Setup is NOT running (might be finished or failed).")

        print("\n--- Last 20 lines of /root/server_setup.log ---")
        stdin, stdout, stderr = client.exec_command("tail -n 20 /root/server_setup.log")
        print(stdout.read().decode())

        stdin, stdout, stderr = client.exec_command("systemctl is-active caddy")
        caddy_status = stdout.read().decode().strip()
        print(f"\nCaddy Status: {caddy_status}")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(check_status())
