import os
import sys
import paramiko

HOST = "207.180.249.220"
USER = "root"
LOCAL_ROOT = os.path.join(os.path.dirname(__file__), "dashboard")
REMOTE_ROOT = "/var/www/dashboard"

def sftp_put_dir(sftp, local_dir, remote_dir):
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
        for f in files:
            lpath = os.path.join(root, f)
            rpath = os.path.join(rdir, f).replace("\\", "/")
            sftp.put(lpath, rpath)

def main():
    if len(sys.argv) < 2:
        print("Usage: python push_dashboard.py <root_password>")
        return 1
    pwd = sys.argv[1]
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=pwd)
    sftp = client.open_sftp()
    sftp_put_dir(sftp, LOCAL_ROOT, REMOTE_ROOT)
    sftp.close()
    for cmd in [
        "systemctl reload caddy"
    ]:
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

