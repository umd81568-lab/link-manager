import sys
import paramiko

HOST = "207.180.249.220"
USER = "root"
LOCAL = "tts_server_local.py"
REMOTE = "/opt/tts/tts_server.py"

def main():
    if len(sys.argv) < 2:
        print("Usage: python push_tts.py <root_password>")
        return 1
    pwd = sys.argv[1]
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=pwd)
    sftp = client.open_sftp()
    sftp.put(LOCAL, REMOTE)
    sftp.close()
    for cmd in ["systemctl daemon-reload", "systemctl restart tts", "systemctl is-active tts"]:
        print(f"\n>>> {cmd}")
        stdin, stdout, stderr = client.exec_command(cmd)
        print(stdout.read().decode(errors="ignore"))
        err = stderr.read().decode(errors="ignore")
        if err:
            print(err)
    client.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())

