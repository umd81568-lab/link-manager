import argparse
import os
import sys

from deploy_config import add_ssh_target_args, connect_ssh_from_args

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_ROOT = os.path.join(BASE_DIR, "dashboard")
REMOTE_ROOT = "/var/www/dashboard"



def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Upload the dashboard directory and reload Caddy.")
    parser.add_argument("password", nargs="?", help="SSH password (optional when using --key-file)")
    add_ssh_target_args(parser)
    return parser.parse_args(argv)



def sftp_put_dir(sftp, local_dir, remote_dir):
    if not os.path.isdir(local_dir):
        raise FileNotFoundError(f"Missing dashboard directory: {local_dir}")

    try:
        sftp.mkdir(remote_dir)
    except Exception:
        pass

    for root, dirs, files in os.walk(local_dir):
        rel = os.path.relpath(root, local_dir)
        rdir = remote_dir if rel == "." else os.path.join(remote_dir, rel).replace("\\", "/")
        try:
            sftp.mkdir(rdir)
        except Exception:
            pass
        for filename in files:
            lpath = os.path.join(root, filename)
            rpath = os.path.join(rdir, filename).replace("\\", "/")
            sftp.put(lpath, rpath)



def main(argv=None):
    args = parse_args(argv)
    try:
        client, _ = connect_ssh_from_args(args, prompt="Enter Server Root Password: ")
    except Exception as exc:
        print(f"SSH connection failed: {exc}")
        return 1

    try:
        sftp = client.open_sftp()
        try:
            sftp_put_dir(sftp, LOCAL_ROOT, REMOTE_ROOT)
        finally:
            sftp.close()
        for cmd in ["systemctl reload caddy"]:
            print(f"\n>>> {cmd}")
            stdin, stdout, stderr = client.exec_command(cmd)
            print(stdout.read().decode(errors="ignore"))
            err = stderr.read().decode(errors="ignore")
            if err:
                print(err)
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
