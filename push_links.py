import sys
import paramiko

HOST = "207.180.249.220"
USER = "root"
LOCAL = "link_manager_local.py"
REMOTE = "/opt/links/link_manager.py"

def main():
    if len(sys.argv) < 2:
        print("Usage: python push_links.py <root_password>")
        return 1
    pwd = sys.argv[1]
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=pwd)
    sftp = client.open_sftp()
    sftp.put(LOCAL, REMOTE)
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
        "systemctl is-active links"
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
