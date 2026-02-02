import paramiko
import sys
import time

HOSTNAME = "207.180.249.220"
USERNAME = "root"
PASSWORD = input("Enter Password: ")

def check_status():
    if not PASSWORD:
        print("No password provided")
        return

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        print(f"Connecting to {HOSTNAME}...")
        client.connect(HOSTNAME, username=USERNAME, password=PASSWORD)
        print("Connected.")
        
        # Check if setup script is running
        stdin, stdout, stderr = client.exec_command("ps aux | grep setup_server.sh | grep -v grep")
        running = stdout.read().decode().strip()
        
        if running:
            print("STATUS: Setup is RUNNING.")
        else:
            print("STATUS: Setup is NOT running (might be finished or failed).")

        # Read last 20 lines of log
        print("\n--- Last 20 lines of /root/server_setup.log ---")
        stdin, stdout, stderr = client.exec_command("tail -n 20 /root/server_setup.log")
        print(stdout.read().decode())
        
        # Check if Caddy is running
        stdin, stdout, stderr = client.exec_command("systemctl is-active caddy")
        caddy_status = stdout.read().decode().strip()
        print(f"\nCaddy Status: {caddy_status}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    check_status()
