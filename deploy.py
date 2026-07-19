import argparse
import os
import sys

import paramiko

from deploy_config import add_ssh_target_args, connect_ssh_from_args

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = 22
LOCAL_SCRIPT = os.path.join(BASE_DIR, "setup_server.sh")
REMOTE_SCRIPT = "/root/setup_server.sh"
LOCAL_DASHBOARD = os.path.join(BASE_DIR, "dashboard")
REMOTE_DASHBOARD = "/var/www/dashboard"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Upload the setup script and dashboard, then run setup_server.sh.")
    parser.add_argument("password", nargs="?", help="SSH password (optional when using --key-file)")
    add_ssh_target_args(parser)
    return parser.parse_args(argv)



def ensure_local_path(path, label):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Missing {label}: {path}")



def upload_files(sftp, local_path, remote_path):
    ensure_local_path(local_path, "upload source")
    if os.path.isfile(local_path):
        print(f"Uploading file: {local_path} -> {remote_path}")
        sftp.put(local_path, remote_path)
        sftp.chmod(remote_path, 0o755)
        return

    if os.path.isdir(local_path):
        print(f"Uploading directory: {local_path} -> {remote_path}")
        try:
            sftp.stat(remote_path)
        except IOError:
            sftp.mkdir(remote_path)

        for item in os.listdir(local_path):
            local_item = os.path.join(local_path, item)
            remote_item = f"{remote_path}/{item}"
            upload_files(sftp, local_item, remote_item)
        return

    raise FileNotFoundError(f"Unsupported path type: {local_path}")



def run_command(client, command):
    print(f"Executing: {command}")
    stdin, stdout, stderr = client.exec_command(command)

    while True:
        line = stdout.readline()
        if not line:
            break
        print(line.strip())

    exit_status = stdout.channel.recv_exit_status()
    if exit_status == 0:
        print("Command executed successfully.")
    else:
        print(f"Error executing command. Exit status: {exit_status}")
        print(stderr.read().decode())



def main(argv=None):
    print("=== Sovereign Guardian Deployment Manager ===")
    args = parse_args(argv)

    try:
        client, settings = connect_ssh_from_args(args, prompt="Enter Server Root Password: ")
        print(f"Connecting to {settings['host']}:{settings['ssh_port']}...", flush=True)
        print("Connected successfully!", flush=True)
    except Exception as exc:
        print(f"Connection failed: {exc}", flush=True)
        return 1

    try:
        ensure_local_path(LOCAL_SCRIPT, "setup script")
        ensure_local_path(LOCAL_DASHBOARD, "dashboard directory")
        sftp = client.open_sftp()
        try:
            upload_files(sftp, LOCAL_SCRIPT, REMOTE_SCRIPT)
            client.exec_command("mkdir -p /var/www")
            upload_files(sftp, LOCAL_DASHBOARD, REMOTE_DASHBOARD)
        finally:
            sftp.close()

        run_command(client, "sed -i 's/\r$//' /root/setup_server.sh")
        run_command(client, "chmod +x /root/setup_server.sh")
        run_command(client, "bash /root/setup_server.sh")
    except Exception as exc:
        print(f"Deployment failed: {exc}")
        return 1
    finally:
        client.close()

    print("\n=== Deployment Completed! ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
