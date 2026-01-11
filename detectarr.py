import os
import subprocess
import psutil
import paramiko
import time
from flask import Flask, render_template
from python_chargepoint import ChargePoint

# Configuration
app = Flask(__name__)  # Looks in ./templates by default
PORT_MONITOR = 2525
HTML_FILE = 'detectarr.html'
DISK_ERROR_THRESHOLD = 80  # percent

# Local machine configuration
LOCAL_MACHINE_NAME = 'MiniMe'
LOCAL_SERVICES = [
    "sonarr", "radarr", "bazarr", "simpleserver", "tailscaled",
    "plexmediaserver", "prowlarr", "jackett", "pihole-FTL", "apcupsd", "alarm"
]
DOCKER_SERVICES = [
    "cleanuparr", "whisperai", "qbittorrent", "diun", "flaresolverr", "qbit-vpn-gluetun-1"
]
DISK_BOOT = '/'
DISK_SECOND = '/media/jon/SSD2'
DISK_THIRD = '/media/jon/HDD'

# Remote machine configuration
REMOTE_MACHINE_NAME = 'Pi'
REMOTE_SERVICES = ["pihole-FTL", "simpleserver", "laundry_alarm"]
REMOTE_SERVICES = [] # make blank so remote server not checked
REMOTE_HOST = '192.168.68.150'
REMOTE_PORT = 22
SSH_USERNAME = 'pi'
SSH_PASSWORD = os.getenv('SSH_PASSWORD', 'REPLACE_ME')  # secure this value

# May want to run the chargepoint command on the remote machine instead of the local machine,
# e.g. if the local machine is on VPN. If so set variables below
REMOTE_CHARGEPOINT = False # to use chargepoint command on remote machine
CHARGEPOINT_COMMAND = "/usr/bin/python /home/pi/apps/chargepoint.py n" # if using remote

# get Chargepoint username and password from environment variables (if using local)
username = os.getenv('USERNAME', 'REPLACE_ME')  # secure this value
password = os.getenv('PASSWORD', 'REPLACE_ME')  # secure this value

def get_status(username,password):
    # Get status of Chargepoint account with provided credentials on local
    # use get_status_remote instead to use remote machine to check ChargePoint
    # Returns (status,color) where:
        # ("Yes","green") if any charger is in use, 
        # ("No","red") if no chargers are in use, or
        # ("Unknown","gray") if an error occurs
    try:
        client = ChargePoint(username,password)
        # Get list of home chargers
        chargers = client.get_home_chargers()

        # Check if each charger is plugged in
        for charger_id in chargers:
            status = client.get_home_charger_status(charger_id)
            # Access the 'plugged_in' attribute directly
            if status.plugged_in: # at least one of the chargers is in use
                return ('Yes','green')
    except:
        return ('Unknown','gray') # error accessing ChargePoint account

    return ('No', 'red') # None of the chargers is in use

def get_status_remote(ssh,timeout=5):
    # Check chargepoint status using remote machine via SSH
    # Returns (status,color) where:
    # ("Yes","green") if any charger is in use, 
    # ("No","red") if no chargers are in use, or
    # ("Unknown","gray") if an error occurs
    charging = invoke_remote_command(ssh, CHARGEPOINT_COMMAND, timeout)

    if "True" in charging:
        return ('Yes','green') # At least one of the chargers is in use
    else: 
        if "False" in charging:
            return ('No', 'red') # None of the chargers is in use
        else:
            print (charging)
            return ('Unknown','gray') # error accessing ChargePoint account

def invoke_remote_command(ssh, command, timeout=5):
    """
    Runs command over SSH and returns output.
    Returns None if it errors out or times out.
    """
    try:
        stdin, stdout, stderr = ssh.exec_command(command)
        channel = stdout.channel
        start_time = time.time()

        while not channel.exit_status_ready():
            if time.time() - start_time > timeout:
                channel.close()
                print(f"Timeout exceeded for command: {command}")
                return None
            time.sleep(0.1)

        # Optionally check if data is ready
        output = stdout.read().decode().strip() if stdout.channel.recv_ready() else ""
        error = stderr.read().decode().strip()
        if error:
            print(f"Remote stderr: {error}")
        return output
    except Exception as e:
        print(f"SSH Command Error: {e}")
        return None

def check_remote_command(ssh, command, expected_output, timeout=5):
    """
    Runs command over SSH and checks if expected_output is in result.
    Returns True if found, False otherwise.
    """
    output = invoke_remote_command(ssh, command, timeout)
    if output is not None:
        return expected_output in output
    return False

def check_local_service(service_name):
    if not service_name.endswith('.service'):
        service_name += '.service'

    def get_status_service(command, use_user_env=False):
        # Create a clean environment copy
        custom_env = os.environ.copy()
        
        if use_user_env:
            # Manually define the session variables needed for background tasks
            uid = os.getuid()
            if 'XDG_RUNTIME_DIR' not in custom_env:
                custom_env['XDG_RUNTIME_DIR'] = f'/run/user/{uid}'
            if 'DBUS_SESSION_BUS_ADDRESS' not in custom_env:
                custom_env['DBUS_SESSION_BUS_ADDRESS'] = f'unix:path=/run/user/{uid}/bus'

        try:
            output = subprocess.check_output(
                command, 
                text=True,
                stderr=subprocess.STDOUT,
                env=custom_env
            )
            
            low_output = output.lower()
            # Catch 'active (running)', 'active (exited)', or just 'active'
            if 'active' in low_output and 'inactive' not in low_output:
                return ('Active', 'green')
            return ('Inactive', 'red')
            
        except subprocess.CalledProcessError as e:
            # If 'Loaded:' is in output, the service exists but is stopped
            if 'loaded:' in e.output.lower():
                return ('Inactive', 'red')
            return e.output 

    # 1. Try System Level
    result = get_status_service(['systemctl', 'status', service_name])
    if isinstance(result, tuple): 
        return result

    # 2. Try User Level (with explicit environment injection)
    result = get_status_service(['systemctl', '--user', 'status', service_name], use_user_env=True)
    if isinstance(result, tuple): 
        return result

    return ('Not Found', 'red')

def get_docker_status(container_name):
    """
    Checks if a Docker container is running.
    Returns True if running, False otherwise.
    """
    try:
        output = subprocess.check_output(
            ["docker", "inspect", "-f", "{{.State.Running}}", container_name],
            stderr=subprocess.STDOUT
        )
        return output.decode().strip().lower() == "true"
    except subprocess.CalledProcessError:
        return False

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
    disk_third, warn_third = check_disk_usage(DISK_THIRD)
    if warn_boot: warnings.append(warn_boot)
    if warn_second: warnings.append(warn_second)
    if warn_third: warnings.append(warn_third)

    # Check local services
    for service in LOCAL_SERVICES:
        status, color = check_local_service(service)
        status_data.append({
            'machine': LOCAL_MACHINE_NAME,
            'name': service,
            'status': status,
            'color': color
        })

    # Check local services
    for docker in DOCKER_SERVICES:
        status, color = ('Active','green') if get_docker_status(docker) else ('Inactive','red')
        status_data.append({
            'machine': LOCAL_MACHINE_NAME,
            'name': docker,
            'status': status,
            'color': color
        })

    # Record the time information was refreshed
    charge_checked_at = time.strftime('%B %d, %Y %H:%M:%S')
    charge_status, charging_color = ('Unknown','gray') # default

    if REMOTE_SERVICES:
        # Check remote services
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh.connect(
                REMOTE_HOST,
                port=REMOTE_PORT,
                username=SSH_USERNAME,
                password=SSH_PASSWORD,
                timeout=10  # connection timeout
                )

            # check chargepoint status, on remote or local, depending on boolean setting
            # removed since chargepoint stopped working 9/2/2025
            # charge_status, charging_color = get_status_remote(ssh,timeout=5) if REMOTE_CHARGEPOINT else get_status(username,password)

            for service in REMOTE_SERVICES:
                command = f"systemctl is-active {service}"
                active = check_remote_command(ssh, command, "active", timeout=5)  # per-command timeout
                status_data.append({
                    'machine': REMOTE_MACHINE_NAME,
                    'name': service,
                    'status': 'Active' if active else 'Inactive',
                    'color': 'green' if active else 'red'
                })

        except Exception as e:
            print(f"SSH Connection Failed: {e}")

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
        disk3=disk_third,
        services=status_data,
        charging=charge_status,
        charging_color=charging_color,
        charge_checked_at=charge_checked_at,
        warnings=warnings
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=PORT_MONITOR)
