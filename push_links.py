import argparse
import os
import sys

from deploy_config import add_ssh_target_args, connect_ssh_from_args

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.join(BASE_DIR, "link_manager_local.py")
REMOTE = "/opt/links/link_manager.py"



def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Upload link_manager_local.py and restart the links service.")
    parser.add_argument("password", nargs="?", help="SSH password (optional when using --key-file)")
    add_ssh_target_args(parser)
    return parser.parse_args(argv)



def main(argv=None):
    args = parse_args(argv)
    if not os.path.isfile(LOCAL):
        print(f"Missing local file: {LOCAL}")
        return 1

    try:
        client, _ = connect_ssh_from_args(args, prompt="Enter Server Root Password: ")
    except Exception as exc:
        print(f"SSH connection failed: {exc}")
        return 1

    try:
        sftp = client.open_sftp()
        try:
            sftp.put(LOCAL, REMOTE)
        finally:
            sftp.close()
        for cmd in [
            "/opt/links/venv/bin/pip install --no-cache-dir requests",
            "bash -lc 'grep -q ^LINK_FREEZE_CREATE= /etc/links.env && sed -i \"s/^LINK_FREEZE_CREATE=.*/LINK_FREEZE_CREATE=0/\" /etc/links.env || echo LINK_FREEZE_CREATE=0 >> /etc/links.env'",
            "bash -lc 'grep -q ^LINK_CREATE_LIMIT= /etc/links.env && sed -i \"s/^LINK_CREATE_LIMIT=.*/LINK_CREATE_LIMIT=10/\" /etc/links.env || echo LINK_CREATE_LIMIT=10 >> /etc/links.env'",
            "bash -lc 'grep -q ^LINK_UPDATE_LIMIT= /etc/links.env && sed -i \"s/^LINK_UPDATE_LIMIT=.*/LINK_UPDATE_LIMIT=200/\" /etc/links.env || echo LINK_UPDATE_LIMIT=200 >> /etc/links.env'",
            "bash -lc 'grep -q ^LINK_SAFE_MODE= /etc/links.env && sed -i \"s/^LINK_SAFE_MODE=.*/LINK_SAFE_MODE=1/\" /etc/links.env || echo LINK_SAFE_MODE=1 >> /etc/links.env'",
            "bash -lc 'which ufw >/dev/null 2>&1 && ufw allow 5002/tcp || true'",
            "systemctl daemon-reload",
            "systemctl restart links",
            "systemctl is-active links",
        ]:
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
