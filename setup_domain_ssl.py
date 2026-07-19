import argparse
import sys

from deploy_config import add_ssh_target_args, connect_ssh_from_args

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



def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Configure Nginx and certbot for a link-manager domain.")
    parser.add_argument("password", nargs="?", help="SSH password (optional when using --key-file)")
    parser.add_argument("domain")
    parser.add_argument("email")
    parser.add_argument("port", nargs="?", type=int, default=5002)
    add_ssh_target_args(parser)
    return parser.parse_args(argv)



def run(client, cmd):
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode(errors="ignore")
    err = stderr.read().decode(errors="ignore")
    return out, err



def main(argv=None):
    args = parse_args(argv)
    try:
        client, _ = connect_ssh_from_args(args, prompt="Enter Server Root Password: ")
    except Exception as exc:
        print(f"SSH connection failed: {exc}")
        return 1

    try:
        out, err = run(client, "bash -lc 'apt-get update -y && apt-get install -y nginx certbot python3-certbot-nginx'")
        print(out or err)

        conf = NGINX_TMPL.format(domain=args.domain, port=args.port)
        sftp = client.open_sftp()
        try:
            with sftp.open(f"/etc/nginx/sites-available/{args.domain}.conf", "w") as handle:
                handle.write(conf)
        finally:
            sftp.close()

        out, err = run(client, f"bash -lc 'ln -sf /etc/nginx/sites-available/{args.domain}.conf /etc/nginx/sites-enabled/{args.domain}.conf'")
        print(out or err)

        out, err = run(client, "bash -lc 'nginx -t'")
        print(out or err)

        out, err = run(client, "systemctl reload nginx")
        print(out or err)

        out, err = run(client, "bash -lc 'which ufw >/dev/null 2>&1 && ufw allow 80 && ufw allow 443 || true'")
        print(out or err)

        out, err = run(client, f"bash -lc 'certbot --nginx -d {args.domain} -m {args.email} --agree-tos -n --redirect'")
        print(out or err)

        out, err = run(client, "systemctl reload nginx")
        print(out or err)

        out, err = run(client, "systemctl is-active nginx")
        print(out or err)

        print({"ok": True, "domain": args.domain, "https": f"https://{args.domain}/"})
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
