import sys
import paramiko

HOST = "207.180.249.220"
USER = "root"

CMD_SEQUENCE = [
    "apt-get update -y",
    "apt-get install -y python3 python3-pip python3-venv",
    "python3 -m venv /opt/tts/venv",
    "/opt/tts/venv/bin/pip install --no-cache-dir flask requests gTTS google-cloud-texttospeech",
    "sed -i 's#ExecStart=/usr/bin/python3 /opt/tts/tts_server.py#ExecStart=/opt/tts/venv/bin/python /opt/tts/tts_server.py#' /etc/systemd/system/tts.service",
    "systemctl daemon-reload",
    "systemctl restart tts",
    "systemctl is-active tts"
]

def main():
    if len(sys.argv) < 2:
        print("Usage: python fix_tts.py <root_password>")
        return 1
    pwd = sys.argv[1]
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=pwd)
    for cmd in CMD_SEQUENCE:
        print(f"\n>>> {cmd}")
        stdin, stdout, stderr = client.exec_command(cmd)
        out = stdout.read().decode(errors="ignore")
        err = stderr.read().decode(errors="ignore")
        print(out)
        if err:
            print(err)
    client.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
