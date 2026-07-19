import getpass
import os

import paramiko

DEFAULT_DEPLOY_HOST = "18.184.78.224"
DEFAULT_DEPLOY_USER = "root"
DEFAULT_DEPLOY_SSH_PORT = 22


def env_value(name):
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def add_ssh_target_args(parser):
    parser.add_argument(
        "--host",
        help=f"SSH host or IP (default: $DEPLOY_HOST or {DEFAULT_DEPLOY_HOST})",
    )
    parser.add_argument(
        "--user",
        help=f"SSH username (default: $DEPLOY_USER or {DEFAULT_DEPLOY_USER})",
    )
    parser.add_argument(
        "--ssh-port",
        dest="ssh_port",
        type=int,
        help=f"SSH port (default: $DEPLOY_SSH_PORT or {DEFAULT_DEPLOY_SSH_PORT})",
    )
    parser.add_argument(
        "--key-file",
        help="SSH private key path (default: $DEPLOY_KEY_FILE)",
    )


def resolve_ssh_target(args):
    host = getattr(args, "host", None) or env_value("DEPLOY_HOST") or DEFAULT_DEPLOY_HOST
    user = getattr(args, "user", None) or env_value("DEPLOY_USER") or DEFAULT_DEPLOY_USER

    ssh_port = getattr(args, "ssh_port", None)
    if ssh_port is None:
        env_port = env_value("DEPLOY_SSH_PORT")
        ssh_port = int(env_port) if env_port else DEFAULT_DEPLOY_SSH_PORT

    key_file = getattr(args, "key_file", None) or env_value("DEPLOY_KEY_FILE")
    return {
        "host": host,
        "user": user,
        "ssh_port": ssh_port,
        "key_file": key_file,
    }


def resolve_ssh_secret(ssh_secret=None, key_file=None, prompt="Enter SSH password: "):
    if ssh_secret:
        return ssh_secret

    env_secret = env_value("DEPLOY_PASSWORD")
    if env_secret:
        return env_secret

    if key_file:
        return None

    return getpass.getpass(prompt)


def connect_ssh(host, user, ssh_port=DEFAULT_DEPLOY_SSH_PORT, ssh_secret=None, key_file=None, timeout=15):
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.RejectPolicy())

    connect_kwargs = {
        "hostname": host,
        "port": ssh_port,
        "username": user,
        "timeout": timeout,
        "allow_agent": True,
        "look_for_keys": True,
    }
    if ssh_secret:
        connect_kwargs["password"] = ssh_secret
    if key_file:
        connect_kwargs["key_filename"] = key_file

    client.connect(**connect_kwargs)
    return client


def connect_ssh_from_args(args, prompt="Enter SSH password: ", timeout=15):
    settings = resolve_ssh_target(args)
    ssh_secret = resolve_ssh_secret(
        ssh_secret=getattr(args, "password", None),
        key_file=settings["key_file"],
        prompt=prompt,
    )
    client = connect_ssh(
        settings["host"],
        settings["user"],
        ssh_port=settings["ssh_port"],
        ssh_secret=ssh_secret,
        key_file=settings["key_file"],
        timeout=timeout,
    )
    return client, settings
