import argparse
import sys

from deploy_config import add_ssh_target_args, connect_ssh_from_args

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



def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Append a Caddy vhost block for the dashboard domain.")
    parser.add_argument("password", nargs="?", help="SSH password (optional when using --key-file)")
    parser.add_argument("domain")
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
        block = TEMPLATE.format(domain=args.domain)
        print(f"\n>>> updating /etc/caddy/Caddyfile with domain: {args.domain}")
        sftp = client.open_sftp()
        try:
            try:
                with sftp.open("/etc/caddy/Caddyfile", "r") as handle:
                    existing = handle.read().decode("utf-8", errors="ignore")
            except Exception:
                existing = ""
            with sftp.open("/etc/caddy/Caddyfile", "w") as handle:
                handle.write(existing + "\n" + block)
        finally:
            sftp.close()
        stdin, stdout, stderr = client.exec_command("systemctl reload caddy")
        print(stdout.read().decode(errors="ignore"))
        err = stderr.read().decode(errors="ignore")
        if err:
            print(err)
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
