import sys
import paramiko

HOST = "207.180.249.220"
USER = "root"

def main():
    if len(sys.argv) < 2:
        print("Usage: python check_tts.py <root_password>")
        return 1
    pwd = sys.argv[1]
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=pwd)
    cmds = [
        "systemctl is-active tts",
        "systemctl status tts --no-pager -l",
        "journalctl -u tts -n 80 --no-pager"
    ]
    for cmd in cmds:
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

