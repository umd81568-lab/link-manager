import sys
import paramiko

HOST = "207.180.249.220"
USER = "root"

TEMPLATE = r"""
{domain} {{
    root * /var/www/dashboard
    file_server
    handle /ords/* {{
        reverse_proxy localhost:8080
    }}
    handle /api/tts* {{
        reverse_proxy localhost:5001
    }}
    handle_path /go/* {{
        reverse_proxy localhost:5002
    }}
}}
http://{domain} {{
    redir https://{{host}}{{uri}} 308
}}
"""

def main():
    if len(sys.argv) < 3:
        print("Usage: python push_caddy_domain.py <root_password> <domain>")
        return 1
    pwd = sys.argv[1]
    domain = sys.argv[2]
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=pwd)
    block = TEMPLATE.format(domain=domain)
    print(f"\n>>> updating /etc/caddy/Caddyfile with domain: {domain}")
    sftp = client.open_sftp()
    try:
        with sftp.open('/etc/caddy/Caddyfile', 'r') as f:
            existing = f.read().decode('utf-8', errors='ignore')
    except Exception:
        existing = ''
    new_content = existing + "\n" + block
    with sftp.open('/etc/caddy/Caddyfile', 'w') as f:
        f.write(new_content)
    sftp.close()
    stdin, stdout, stderr = client.exec_command('systemctl reload caddy')
    print(stdout.read().decode(errors='ignore'))
    err = stderr.read().decode(errors='ignore')
    if err:
        print(err)
    client.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
