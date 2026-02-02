import paramiko
import os
import getpass
import time
import sys

# Configuration
HOSTNAME = "207.180.249.220"
USERNAME = "root"
PORT = 22
LOCAL_SCRIPT = "setup_server.sh"
REMOTE_SCRIPT = "/root/setup_server.sh"
LOCAL_DASHBOARD = "dashboard"
REMOTE_DASHBOARD = "/var/www/dashboard"

def create_ssh_client(password):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        print(f"Connecting to {HOSTNAME}...", flush=True)
        client.connect(HOSTNAME, port=PORT, username=USERNAME, password=password)
        print("Connected successfully!", flush=True)
        return client
    except Exception as e:
        print(f"Connection failed: {e}", flush=True)
        return None

def upload_files(sftp, local_path, remote_path):
    try:
        # Check if local path is file or directory
        if os.path.isfile(local_path):
            print(f"Uploading file: {local_path} -> {remote_path}")
            sftp.put(local_path, remote_path)
            sftp.chmod(remote_path, 0o755) # Make executable
        elif os.path.isdir(local_path):
            print(f"Uploading directory: {local_path} -> {remote_path}")
            # Create remote dir if not exists
            try:
                sftp.stat(remote_path)
            except IOError:
                sftp.mkdir(remote_path)
            
            for item in os.listdir(local_path):
                local_item = os.path.join(local_path, item)
                remote_item = f"{remote_path}/{item}"
                upload_files(sftp, local_item, remote_item)
    except Exception as e:
        print(f"Upload failed for {local_path}: {e}")

def run_command(client, command):
    print(f"Executing: {command}")
    stdin, stdout, stderr = client.exec_command(command)
    
    # Stream output
    while True:
        line = stdout.readline()
        if not line:
            break
        print(line.strip())
    
    exit_status = stdout.channel.recv_exit_status()
    if exit_status == 0:
        print("Command executed successfully.")
    else:
        print(f"Error executing command. Exit status: {exit_status}")
        print(stderr.read().decode())

def main():
    print("=== Sovereign Guardian Deployment Manager ===")
    print(f"Target Server: {HOSTNAME}")
    
    # Get password securely
    if len(sys.argv) > 1:
        password = sys.argv[1]
    else:
        password = getpass.getpass("Enter Server Root Password: ")

    if not password:
        print("Password cannot be empty.")
        return

    client = create_ssh_client(password)
    if not client:
        return

    sftp = client.open_sftp()

    # 1. Upload setup script
    upload_files(sftp, LOCAL_SCRIPT, REMOTE_SCRIPT)

    # 2. Upload Dashboard
    # First ensure /var/www exists
    try:
        client.exec_command("mkdir -p /var/www")
    except:
        pass
    upload_files(sftp, LOCAL_DASHBOARD, REMOTE_DASHBOARD)

    sftp.close()

    # 3. Run Setup Script
    # Convert to Unix line endings just in case
    run_command(client, "sed -i 's/\r$//' /root/setup_server.sh")
    run_command(client, "chmod +x /root/setup_server.sh")
    run_command(client, "bash /root/setup_server.sh")

    client.close()
    print("\n=== Deployment Completed! ===")

if __name__ == "__main__":
    main()
