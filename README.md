# Detectarr

**Detectarr** is a lightweight, Flask-based service monitor for tracking the status of key media server applications and system resources across local and remote machines.

## 🔍 Features

- Web-based dashboard to monitor:
  - System services (Sonarr, Radarr, Plex, etc.)
  - CPU and memory usage
  - Disk usage (boot and secondary drives)
  - Remote service status via SSH
  - Car charging status (via custom remote Python script)
- Light and dark mode support
- Responsive (mobile-friendly) layout

---

## 🚀 Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/jonstaebell/detectarr-public.git
cd detectarr-public

2. Install Dependencies

Make sure you have Python 3 installed. Then install the required Python packages:

pip install -r requirements.txt

If requirements.txt is not included, manually install:

pip install flask psutil paramiko

3. Run the App

You need to create a bash script, and set the ssh password for the remote machine before starting detectarr.
For example, create a file called detectarr.sh:
  #!/bin/bash
  export SSH_PASSWORD='1234'
  python detectarr.py

Then open your browser to:
http://localhost:2525
⚙️ Configuration

Edit the detectarr.py file to configure:

    services: List of systemd services to monitor locally

    remote_host, username: For SSH access to a remote machine

    chargepoint_command: Python script to check EV charger status

    Disk mount points and error thresholds

Example:

services = ["nordvpnd", "sonarr", "radarr"]
remote_host = '192.168.68.150'
username = 'pi'
password = 'your_password'
chargepoint_command = "/usr/bin/python /home/pi/apps/chargepoint.py n"

🖥️ Systemd Integration (Optional)

You can run Detectarr as a background service using systemd.
Create a service file:

[Unit]
Description=Detectarr Service Monitor
After=network.target

[Service]
ExecStart=/home/jon/projects/detectarr/detectarr.sh
WorkingDirectory=/home/jon/projects/detectarr
Restart=on-failure
User=jon

[Install]
WantedBy=multi-user.target

Enable and start the service:

sudo systemctl daemon-reload
sudo systemctl enable detectarr.service
sudo systemctl start detectarr.service

📁 Folder Structure

detectarr-public/
├── detectarr.py          # Main Flask app
├── templates/
│   └── detectarr.html    # Web dashboard template
├── static/
│   └── favicon.ico       # Optional favicon
├── detectarr.sh          # (Optional) Bash wrapper script
└── README.md

🛡️ License

This project is open source and available under the MIT License.
🙏 Credits

Developed by @jonstaebell
