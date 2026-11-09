#!/usr/bin/env bash
# One-time setup of the Raspberry Pi 5 for Ai-Vacuwise's two cameras.
#   Camera Module 3 (ribbon cable) -> pre-registration camera service (port 8080, starts at boot)
#   USB webcam                     -> entrance recognizer (entrance_client/recognize.py)
#
# Run ON THE PI, from the folder that was copied from the laptop:
#     cd ~/ai-vacuwise-pi && bash pi_camera/setup_pi5.sh
# Safe to run again.

set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)"
ME="$(id -un)"
echo "== Ai-Vacuwise Raspberry Pi 5 camera setup (folder: $DIR, user: $ME) =="

# sudo password typed visibly (hidden password prompts do not work reliably on this setup)
read -r -p "Pi password for sudo (it will show on screen): " PW
echo "$PW" | sudo -S -v 2>/dev/null || { echo "Stopped: wrong password."; exit 1; }
unset PW

# 1. System packages: picamera2 for the Camera Module 3, v4l-utils to list cameras
sudo apt-get update -y
sudo apt-get install -y python3-picamera2 v4l-utils
echo "OK  picamera2 and v4l-utils installed"

# 2. Python packages for face recognition (prebuilt wheels; no slow source builds on the Pi)
PIP="python3 -m pip install --break-system-packages"
python3 -c "import dlib" 2>/dev/null || $PIP dlib-bin
python3 -c "import face_recognition" 2>/dev/null || $PIP --no-deps face_recognition==1.3.0
$PIP Click Pillow numpy opencv-python "requests==2.31.0"
python3 -c "import face_recognition_models" 2>/dev/null || $PIP --resume-retries 5 face_recognition_models
python3 -c "import face_recognition, cv2, picamera2, requests; print('OK  Python packages ready')"

# 3. Entrance settings for the Pi 5 (laptop address, USB webcam)
cp "$DIR/entrance_client/config_pi5.py" "$DIR/entrance_client/config.py"
echo "OK  entrance_client/config.py set for the Pi 5 (backend http://192.168.100.200:8000, USB webcam)"

# 4. Pre-registration camera service, starts at boot
sudo tee /etc/systemd/system/ai-vacuwise-prereg-camera.service >/dev/null <<UNIT
[Unit]
Description=Ai-Vacuwise pre-registration camera (Camera Module 3)
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
sudo systemctl daemon-reload
sudo systemctl enable --now ai-vacuwise-prereg-camera
echo "OK  pre-registration camera service started"

# 5. Checks
echo
echo "Cameras the Pi can see:"
v4l2-ctl --list-devices 2>/dev/null | grep -v "^\s*$" | grep -iE "usb|imx708|camera|unicam|rp1" || true
sleep 4
echo
echo "Pre-registration camera says: $(curl -s http://127.0.0.1:8080/health || echo 'not responding')"
IP="$(hostname -I | awk '{print $1}')"
echo
echo "Done. This Pi's address: $IP"
echo "  Pre-Registration page -> Camera: Raspberry Pi camera, address: http://$IP:8080"
echo "  Entrance camera       -> cd $DIR/entrance_client && python3 recognize.py"
