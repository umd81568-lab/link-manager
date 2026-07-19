import argparse
import os
import sys

from deploy_config import add_ssh_target_args, connect_ssh_from_args

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.join(BASE_DIR, "tts_server_local.py")
REMOTE = "/opt/tts/tts_server.py"



def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Upload the TTS server file and restart the TTS service.")
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
        for cmd in ["systemctl daemon-reload", "systemctl restart tts", "systemctl is-active tts"]:
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
