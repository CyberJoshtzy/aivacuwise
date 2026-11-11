#!/usr/bin/env bash
# Installs the two AiVacuwise camera services on the Raspberry Pi 5. Both start at boot.
#   aivacuwise-prereg-camera    Camera Module 3, shared with the Pre-Registration page (port 8080)
#   aivacuwise-entrance-camera  USB webcam, recognizes evacuees at the entrance (no window)
# Run ON THE PI:  cd ~/aivacuwise-pi && bash pi_camera/install_services.sh
# Needs sudo; if you are not asked for the password, sudo is already unlocked.

set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)"
ME="$(id -un)"

if ! sudo -n true 2>/dev/null; then
  read -r -p "Pi password for sudo (it will show on screen): " PW
  echo "$PW" | sudo -S -v 2>/dev/null || { echo "Stopped: wrong password."; exit 1; }
  unset PW
fi

sudo tee /etc/systemd/system/aivacuwise-prereg-camera.service >/dev/null <<UNIT
[Unit]
Description=AiVacuwise pre-registration camera (Camera Module 3)
After=network-online.target
Wants=network-online.target

[Service]
User=$ME
WorkingDirectory=$DIR/pi_camera
ExecStart=/usr/bin/python3 $DIR/pi_camera/prereg_camera.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

sudo tee /etc/systemd/system/aivacuwise-entrance-camera.service >/dev/null <<UNIT
[Unit]
Description=AiVacuwise entrance camera (USB webcam, face recognition)
After=network-online.target
Wants=network-online.target

[Service]
User=$ME
WorkingDirectory=$DIR/entrance_client
Environment=AIVACUWISE_HEADLESS=1
Environment=PYTHONUNBUFFERED=1
ExecStart=/usr/bin/python3 $DIR/entrance_client/recognize.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable aivacuwise-prereg-camera aivacuwise-entrance-camera >/dev/null 2>&1
sudo systemctl restart aivacuwise-prereg-camera aivacuwise-entrance-camera
echo "OK  both camera services installed and started (they also start at boot)"
sleep 8
echo
echo "Pre-registration camera: $(curl -s http://127.0.0.1:8080/health || echo 'not responding')"
echo "Entrance camera (last lines of its log):"
sudo journalctl -u aivacuwise-entrance-camera -n 4 --no-pager -o cat || true
echo
echo "To watch the entrance camera log:  sudo journalctl -u aivacuwise-entrance-camera -f"
echo "To use the camera window instead:  sudo systemctl stop aivacuwise-entrance-camera"
echo "                                   then: cd $DIR/entrance_client && python3 recognize.py"
