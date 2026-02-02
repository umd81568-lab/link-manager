import sys
import paramiko

HOST = "207.180.249.220"
USER = "root"

NGINX_TMPL = """
server {
    listen 80;
    server_name {domain};
    location / {
        proxy_pass http://127.0.0.1:{port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
"""

def run(client, cmd):
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode(errors="ignore")
    err = stderr.read().decode(errors="ignore")
    return out, err

def main():
    if len(sys.argv) < 4:
        print("Usage: python setup_domain_ssl.py <root_password> <domain> <email> [port=5002]")
        return 1
    pwd = sys.argv[1]
    domain = sys.argv[2]
    email = sys.argv[3]
    port = int(sys.argv[4]) if len(sys.argv) > 4 else 5002

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=pwd)

    out, err = run(client, "bash -lc 'apt-get update -y && apt-get install -y nginx certbot python3-certbot-nginx'"
    )
    print(out or err)

    conf = NGINX_TMPL.format(domain=domain, port=port)
    sftp = client.open_sftp()
    with sftp.open(f"/etc/nginx/sites-available/{domain}.conf", "w") as f:
        f.write(conf)
    sftp.close()

    out, err = run(client, f"bash -lc 'ln -sf /etc/nginx/sites-available/{domain}.conf /etc/nginx/sites-enabled/{domain}.conf'"
    )
    print(out or err)

    out, err = run(client, "bash -lc 'nginx -t'"
    )
    print(out or err)

    out, err = run(client, "systemctl reload nginx")
    print(out or err)

    out, err = run(client, f"bash -lc 'which ufw >/dev/null 2>&1 && ufw allow 80 && ufw allow 443 || true'"
    )
    print(out or err)

    out, err = run(client, f"bash -lc 'certbot --nginx -d {domain} -m {email} --agree-tos -n --redirect'"
    )
    print(out or err)

    out, err = run(client, "systemctl reload nginx")
    print(out or err)

    out, err = run(client, "systemctl is-active nginx")
    print(out or err)

    client.close()
    print({"ok": True, "domain": domain, "https": f"https://{domain}/"})
    return 0

if __name__ == "__main__":
    sys.exit(main())

