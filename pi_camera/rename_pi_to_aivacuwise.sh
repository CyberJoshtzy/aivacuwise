#!/usr/bin/env bash
# Renames the Raspberry Pi 5 from "ai-vacuwise" to "aivacuwise".
#
# Run ON THE PI, while signed in as the old user ai-vacuwise:
#     echo 'PI_PASSWORD' | sudo -S bash /home/ai-vacuwise/rename_pi_to_aivacuwise.sh
#
# What it does:
#   1. Creates the user "aivacuwise" with the SAME password and the same groups
#      (camera, video, sudo, ...) as "ai-vacuwise".
#   2. Copies the project folder to /home/aivacuwise/aivacuwise-pi (and the old user's
#      ~/.local, where pip packages may live). The old folder is NOT deleted.
#   3. Replaces the camera services with aivacuwise-prereg-camera and
#      aivacuwise-entrance-camera, running as the new user from the new folder.
#   4. Changes the hostname to aivacuwise-pi.
# The old user ai-vacuwise is kept until you have checked everything works.
# Restart the Pi afterwards:  sudo reboot

set -e
OLD_USER="ai-vacuwise"
NEW_USER="aivacuwise"
OLD_DIR="/home/$OLD_USER/ai-vacuwise-pi"
NEW_HOME="/home/$NEW_USER"
NEW_DIR="$NEW_HOME/aivacuwise-pi"
NEW_HOST="aivacuwise-pi"

if [ "$(id -u)" != 0 ]; then
  echo "Stopped: run this with sudo."
  exit 1
fi
if [ ! -d "$OLD_DIR" ]; then
  echo "Stopped: $OLD_DIR was not found."
  exit 1
fi
echo "== AiVacuwise rename (Raspberry Pi) =="

# 1. New user with the same password and groups
if id "$NEW_USER" >/dev/null 2>&1; then
  echo "OK  user $NEW_USER already exists"
else
  GROUPS_LIST="$(id -nG "$OLD_USER" | tr ' ' '\n' | grep -vx "$OLD_USER" | paste -sd, -)"
  useradd -m -s /bin/bash -G "$GROUPS_LIST" "$NEW_USER"
  usermod -p "$(getent shadow "$OLD_USER" | cut -d: -f2)" "$NEW_USER"
  echo "OK  user $NEW_USER created (same password, groups: $GROUPS_LIST)"
fi

# 2. Copy the project (and pip packages installed for the old user, if any)
if [ -d "$NEW_DIR" ]; then
  echo "OK  $NEW_DIR already exists (not copied again)"
else
  cp -a "$OLD_DIR" "$NEW_DIR"
  echo "OK  project copied to $NEW_DIR"
fi
if [ -d "/home/$OLD_USER/.local" ] && [ ! -d "$NEW_HOME/.local" ]; then
  cp -a "/home/$OLD_USER/.local" "$NEW_HOME/.local"
  echo "OK  copied ~/.local (pip packages)"
fi
chown -R "$NEW_USER:$NEW_USER" "$NEW_HOME"

# 3. Camera services under the new names
for old in ai-vacuwise-prereg-camera ai-vacuwise-entrance-camera; do
  systemctl stop "$old" 2>/dev/null || true
  systemctl disable "$old" >/dev/null 2>&1 || true
  rm -f "/etc/systemd/system/$old.service"
done

cat > /etc/systemd/system/aivacuwise-prereg-camera.service <<UNIT
[Unit]
Description=AiVacuwise pre-registration camera (Camera Module 3)
After=network-online.target
Wants=network-online.target

[Service]
User=$NEW_USER
WorkingDirectory=$NEW_DIR/pi_camera
ExecStart=/usr/bin/python3 $NEW_DIR/pi_camera/prereg_camera.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/systemd/system/aivacuwise-entrance-camera.service <<UNIT
[Unit]
Description=AiVacuwise entrance camera (USB webcam, face recognition)
After=network-online.target
Wants=network-online.target

[Service]
User=$NEW_USER
WorkingDirectory=$NEW_DIR/entrance_client
Environment=AIVACUWISE_HEADLESS=1
Environment=PYTHONUNBUFFERED=1
ExecStart=/usr/bin/python3 $NEW_DIR/entrance_client/recognize.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable aivacuwise-prereg-camera aivacuwise-entrance-camera >/dev/null 2>&1
echo "OK  services aivacuwise-prereg-camera and aivacuwise-entrance-camera installed (start after the restart)"

# Desktop auto-login, if it was set to the old user
if [ -f /etc/lightdm/lightdm.conf ] && grep -q "autologin-user=$OLD_USER" /etc/lightdm/lightdm.conf; then
  sed -i "s/autologin-user=$OLD_USER/autologin-user=$NEW_USER/" /etc/lightdm/lightdm.conf
  echo "OK  desktop auto-login now uses $NEW_USER"
fi

# 4. Hostname
OLD_HOST="$(hostname)"
hostnamectl set-hostname "$NEW_HOST"
sed -i "s/\b$OLD_HOST\b/$NEW_HOST/g" /etc/hosts
echo "OK  hostname changed from $OLD_HOST to $NEW_HOST"

echo
echo "Done. Restart the Pi now:  sudo reboot"
echo "Then connect as the new user:  ssh aivacuwise@192.168.100.41  (same password)"
