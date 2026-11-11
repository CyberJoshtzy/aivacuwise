#!/usr/bin/env bash
# One-time setup of the Raspberry Pi 5 for AiVacuwise's two cameras.
#   Camera Module 3 (ribbon cable) -> pre-registration camera service (port 8080, starts at boot)
#   USB webcam                     -> entrance recognizer (entrance_client/recognize.py)
#
# Run ON THE PI, from the folder that was copied from the laptop:
#     cd ~/aivacuwise-pi && bash pi_camera/setup_pi5.sh
# Safe to run again.

set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)"
ME="$(id -un)"
echo "== AiVacuwise Raspberry Pi 5 camera setup (folder: $DIR, user: $ME) =="

# sudo password typed visibly (hidden password prompts do not work reliably on this setup)
read -r -p "Pi password for sudo (it will show on screen): " PW
echo "$PW" | sudo -S -v 2>/dev/null || { echo "Stopped: wrong password."; exit 1; }
unset PW

# 1. System packages. numpy, OpenCV, requests and Pillow come from apt so they match the
#    system picamera2 (a newer pip numpy can break the Camera Module 3 library).
sudo apt-get update -y
sudo apt-get install -y python3-picamera2 python3-opencv python3-numpy python3-requests \
    python3-pil python3-click python3-setuptools v4l-utils
echo "OK  system packages installed (picamera2, OpenCV, numpy, requests)"

# Remove copies that an earlier run put in ~/.local (they would hide the system versions)
for p in numpy opencv-python requests; do
  python3 -m pip uninstall -y --break-system-packages "$p" >/dev/null 2>&1 || true
done

# 2. Face recognition (prebuilt wheels; no slow source builds on the Pi)
PIP="python3 -m pip install --break-system-packages --no-warn-script-location"
python3 -c "import dlib" 2>/dev/null || $PIP dlib-bin
python3 -c "import face_recognition" 2>/dev/null || $PIP --no-deps face_recognition==1.3.0
# about 100 MB; retry if the connection drops
for i in 1 2 3; do
  python3 -c "import face_recognition_models" 2>/dev/null && break
  $PIP --no-deps face_recognition_models || sleep 5
done
python3 -c "import face_recognition, cv2, numpy, picamera2, requests; print('OK  Python packages ready (numpy %s, OpenCV %s)' % (numpy.__version__, cv2.__version__))"

# 3. Entrance settings for the Pi 5 (laptop address, USB webcam)
cp "$DIR/entrance_client/config_pi5.py" "$DIR/entrance_client/config.py"
echo "OK  entrance_client/config.py set for the Pi 5 (backend http://192.168.100.200:8000, USB webcam)"

# 4. Camera services (pre-registration + entrance), start at boot
bash "$DIR/pi_camera/install_services.sh"

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
echo "  Entrance camera       -> runs by itself (service aivacuwise-entrance-camera)"
