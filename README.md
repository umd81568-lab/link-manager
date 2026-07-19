# link-manager deployment runbook

## Prerequisites
- Python 3.10+ required.
- Install Python dependencies before running deploy scripts:
  - `python -m pip install -r requirements.txt paramiko`
- Server assumptions:
  - SSH access to the target host (default user: `root`)
  - `systemd` available for `links`, `tts`, `nginx`, and/or `caddy`
  - Project files are run from this repository checkout

## Host configuration
All updated deployment/status scripts now resolve the target in this order:
1. `--host`
2. `DEPLOY_HOST`
3. default `18.184.78.224`

Related SSH options:
- `--user` / `DEPLOY_USER` (default `root`)
- `--ssh-port` / `DEPLOY_SSH_PORT` (default `22`)
- `--key-file` / `DEPLOY_KEY_FILE`
- password from positional arg or `DEPLOY_PASSWORD`
- SSH host keys are validated against `~/.ssh/known_hosts`; for a first-time connection, run `ssh root@18.184.78.224` once and confirm the fingerprint.

## Common commands
Deploy the main app update with password auth:
```bash
python deploy_all.py my-root-password --host 18.184.78.224
```

Deploy with key auth:
```bash
DEPLOY_HOST=18.184.78.224 python deploy_all.py --key-file ~/.ssh/id_rsa
```

Deploy with domain/email/port overrides:
```bash
python deploy_all.py my-root-password example.com admin@example.com 5002 --host 18.184.78.224
```

Upload and run the full setup helper:
```bash
python deploy.py my-root-password --host 18.184.78.224
```

Upload dashboard only:
```bash
python push_dashboard.py my-root-password --host 18.184.78.224
```

Check remote services:
```bash
python remote_check.py my-root-password --host 18.184.78.224
python check_tts.py my-root-password --host 18.184.78.224
```

Windows PowerShell helper:
```powershell
powershell -ExecutionPolicy Bypass -File .\deploy.ps1 -ServerIP 18.184.78.224
```

## Running from SSH/panel
- `cd /home/runner/work/link-manager/link-manager` first, or use full script paths as shown above.
- The Python scripts now resolve local files relative to the script location, so they are safer to run from a panel or another current working directory.
- `deploy_all.py` fails early if `link_manager_local.py` is missing instead of uploading partially.
- If this is the first SSH connection from the machine, add the server key to `~/.ssh/known_hosts` first (for example by running `ssh root@18.184.78.224` once and confirming the fingerprint).

## Default services and ports
- `links` app: `5002`
- `tts` service: `5001`
- ORDS: `8080`
- HTTP/HTTPS reverse proxy: `80` / `443`

## Troubleshooting
- **SSH auth failed**
  - Re-check `--host`, `--user`, and `--ssh-port`
  - Try `--key-file /path/to/key` or export `DEPLOY_PASSWORD`
  - Confirm the server allows SSH login for the selected user
- **Missing local files**
  - Ensure `link_manager_local.py`, `tts_server_local.py`, `setup_server.sh`, and `dashboard/` exist in this repository checkout
  - Re-run from the repo or keep using absolute script paths
- **Service inactive after deploy**
  - Run `python remote_check.py ... --host <ip>`
  - Run `python check_tts.py ... --host <ip>` for TTS-specific issues
  - Check `systemctl status links`, `systemctl status caddy`, `systemctl status nginx`, or `journalctl -u <service>` on the server
- **Port conflicts**
  - Check listeners with `ss -ltnp | grep ':80\|:443\|:5001\|:5002\|:8080'`
  - Stop or reconfigure the conflicting service before retrying
- **ORDS not listening**
  - Review `/var/log/ords.log`
  - Re-run `python remote_fix_ords.py ... --host <ip>` if needed
