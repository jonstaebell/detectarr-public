import os
import subprocess
import psutil
import paramiko
import time
from flask import Flask, render_template

# Configuration
app = Flask(__name__)  # Looks in ./templates by default
PORT_MONITOR = 2525
HTML_FILE = 'detectarr.html'
DISK_ERROR_THRESHOLD = 80  # percent

# Local machine configuration
LOCAL_MACHINE_NAME = 'MiniMe'
LOCAL_SERVICES = [
    "nordvpnd", "qbittorrent-nox@jon", "sonarr", "radarr", "bazarr",
    "plexmediaserver", "decluttarr", "prowlarr", "jackett", "pihole-FTL"
]
DISK_BOOT = '/'
DISK_SECOND = '/media/jon/SSD2'

# Remote machine configuration
REMOTE_MACHINE_NAME = 'Pi'
REMOTE_SERVICES = ["pihole-FTL", "simpleserver", "laundry_alarm"]
REMOTE_HOST = '192.168.68.150'
REMOTE_PORT = 22
SSH_USERNAME = 'pi'
SSH_PASSWORD = os.getenv('SSH_PASSWORD', 'REPLACE_ME')  # secure this value
CHARGEPOINT_COMMAND = "/usr/bin/python /home/pi/apps/chargepoint.py n"

def check_remote_command(ssh, command, expected_output):
    """
    Runs command over SSH and checks if expected_output is in result.
    Returns True if found, False otherwise.
    """
    try:
        stdin, stdout, stderr = ssh.exec_command(command)
        output = stdout.read().decode().strip()
        error = stderr.read().decode().strip()
        if error:
            print(f"Remote error: {error}")
        return expected_output in output and not error
    except Exception as e:
        print(f"SSH Command Error: {e}")
        return False

def check_local_service(service_name):
    """
    Checks local systemd service status.
    Returns (status_text, color).
    """
    try:
        output = subprocess.check_output(['systemctl', 'status', service_name], text=True)
        return ('Active', 'green') if 'active (running)' in output else ('Inactive', 'red')
    except subprocess.CalledProcessError:
        return ('Not Found', 'red')

def check_disk_usage(disk_path):
    """
    Returns disk usage info and warning message if over threshold.
    """
    usage = psutil.disk_usage(disk_path)
    warning = None
    if usage.percent > DISK_ERROR_THRESHOLD:
        warning = f"Disk {disk_path} usage high: {usage.percent}%"
    return usage, warning

@app.route('/')
def index():
    status_data = []
    warnings = []

    # Local system info
    cpu_percent = psutil.cpu_percent()
    memory_info = psutil.virtual_memory()

    disk_boot, warn_boot = check_disk_usage(DISK_BOOT)
    disk_second, warn_second = check_disk_usage(DISK_SECOND)
    if warn_boot: warnings.append(warn_boot)
    if warn_second: warnings.append(warn_second)

    # Check local services
    for service in LOCAL_SERVICES:
        status, color = check_local_service(service)
        status_data.append({
            'machine': LOCAL_MACHINE_NAME,
            'name': service,
            'status': status,
            'color': color
        })

    # Check remote services
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(REMOTE_HOST, port=REMOTE_PORT, username=SSH_USERNAME, password=SSH_PASSWORD)

        for service in REMOTE_SERVICES:
            command = f"systemctl is-active {service}"
            active = check_remote_command(ssh, command, "active")
            status_data.append({
                'machine': REMOTE_MACHINE_NAME,
                'name': service,
                'status': 'Active' if active else 'Inactive',
                'color': 'green' if active else 'red'
            })

        # Check chargepoint status
        charging = check_remote_command(ssh, CHARGEPOINT_COMMAND, "True")
        charge_status = 'Yes' if charging else 'No'
        charging_color = 'green' if charging else 'red'

    except Exception as e:
        print(f"SSH Connection Failed: {e}")
        charge_status = 'Unknown'
        charging_color = 'gray'
        for service in REMOTE_SERVICES:
            status_data.append({
                'machine': REMOTE_MACHINE_NAME,
                'name': service,
                'status': 'Connection Failed',
                'color': 'gray'
            })
    finally:
        ssh.close()

    return render_template(
        HTML_FILE,
        cpu=cpu_percent,
        memory=memory_info,
        disk=disk_boot,
        disk2=disk_second,
        services=status_data,
        charging=charge_status,
        charging_color=charging_color,
        warnings=warnings
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=PORT_MONITOR)
