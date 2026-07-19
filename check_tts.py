import argparse
import sys

from deploy_config import add_ssh_target_args, connect_ssh_from_args



def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Check remote TTS service status.")
    parser.add_argument("password", nargs="?", help="SSH password (optional when using --key-file)")
    add_ssh_target_args(parser)
    return parser.parse_args(argv)



def main(argv=None):
    args = parse_args(argv)
    try:
        client, _ = connect_ssh_from_args(args, prompt="Enter Server Root Password: ")
    except Exception as exc:
        print(f"SSH connection failed: {exc}")
        return 1

    cmds = [
        "systemctl is-active tts",
        "systemctl status tts --no-pager -l",
        "journalctl -u tts -n 80 --no-pager",
    ]
    try:
        for cmd in cmds:
            print(f"\n>>> {cmd}")
            stdin, stdout, stderr = client.exec_command(cmd)
            out = stdout.read().decode(errors="ignore")
            err = stderr.read().decode(errors="ignore")
            print(out)
            if err:
                print(err)
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
