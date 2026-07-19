import argparse
import sys

from deploy_config import add_ssh_target_args, connect_ssh_from_args

CMD_SEQUENCE = [
    "apt-get update -y",
    "apt-get install -y python3 python3-pip python3-venv",
    "python3 -m venv /opt/tts/venv",
    "/opt/tts/venv/bin/pip install --no-cache-dir flask requests gTTS google-cloud-texttospeech",
    "sed -i 's#ExecStart=/usr/bin/python3 /opt/tts/tts_server.py#ExecStart=/opt/tts/venv/bin/python /opt/tts/tts_server.py#' /etc/systemd/system/tts.service",
    "systemctl daemon-reload",
    "systemctl restart tts",
    "systemctl is-active tts",
]



def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Repair the remote TTS service environment.")
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

    try:
        for cmd in CMD_SEQUENCE:
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
