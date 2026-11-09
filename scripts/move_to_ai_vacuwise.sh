#!/usr/bin/env bash
# Moves the project folder from ~/bilislikas2.0 to ~/ai-vacuwise on the laptop server.
#
# Run from your home folder (not from inside the project):
#     cd ~ && bash ~/bilislikas2.0/scripts/move_to_ai_vacuwise.sh
#
# What it does:
#   1. Checks that the database volume exists, so no data is lost.
#   2. Stops the backend service.
#   3. Moves the folder and leaves a shortcut (symlink) at ~/bilislikas2.0,
#      so the venv and any old commands keep working.
#   4. Points the systemd service(s) to the new folder and starts the backend again.
#   5. Checks that the server answers.
# The Docker database keeps running the whole time; its data is not touched.

set -e
OLD="$HOME/bilislikas2.0"
NEW="$HOME/ai-vacuwise"
ME="$(id -un)"

echo "== Ai-Vacuwise folder move =="

if [ -L "$OLD" ]; then
  echo "Already done: $OLD is a shortcut to $(readlink "$OLD")."
  exit 0
fi
if [ ! -d "$OLD" ]; then
  echo "Stopped: $OLD was not found."
  exit 1
fi
if [ -e "$NEW" ]; then
  echo "Stopped: $NEW already exists. Rename or remove it first."
  exit 1
fi

# 1. Database volume check
if ! docker volume ls --format '{{.Name}}' | grep -qx 'bilislikas20_postgres_data'; then
  echo "Stopped: Docker volume 'bilislikas20_postgres_data' was not found."
  echo "Your volumes are:"
  docker volume ls
  echo "Send this list to Claude before moving the folder."
  exit 1
fi
echo "OK  database volume bilislikas20_postgres_data found"

# Make sure the latest code (with the fixed Docker project name) is here
git -C "$OLD" pull --ff-only origin main
grep -q '^name: bilislikas20' "$OLD/docker-compose.yml" || { echo "Stopped: docker-compose.yml has no fixed project name yet."; exit 1; }
echo "OK  docker-compose.yml keeps the database name"

# sudo password (typed visibly, because hidden password prompts do not work on this laptop)
read -r -p "Laptop password for sudo (it will show on screen): " PW
echo "$PW" | sudo -S -v 2>/dev/null || { echo "Stopped: wrong password."; exit 1; }
unset PW

# 2. Stop backend (and sync agent if installed)
sudo systemctl stop bilislikas
SYNC=0
if [ -f /etc/systemd/system/bilislikas-sync.service ]; then
  SYNC=1
  sudo systemctl stop bilislikas-sync || true
fi
echo "OK  services stopped"

# 3. Move the folder and leave a shortcut at the old path
mv "$OLD" "$NEW"
ln -s "$NEW" "$OLD"
echo "OK  moved to $NEW (shortcut left at $OLD)"

# 4. Point systemd to the new folder
for svc in bilislikas bilislikas-sync; do
  f="/etc/systemd/system/$svc.service"
  if [ -f "$f" ]; then
    sudo sed -i "s#/home/$ME/bilislikas2\.0#/home/$ME/ai-vacuwise#g" "$f"
    echo "OK  updated $f"
  fi
done
sudo systemctl daemon-reload
sudo systemctl start bilislikas
[ "$SYNC" = 1 ] && sudo systemctl start bilislikas-sync || true
echo "OK  services started"

# 5. Check
sleep 10
echo "Server says: $(curl -s http://127.0.0.1:8000)"
echo
echo "Done. Now run:  cd ~/ai-vacuwise && source venv/bin/activate"
echo "In VS Code: File > Open Folder > ai-vacuwise"
echo "For Railway: run 'railway link' once inside ~/ai-vacuwise and pick the bilislikas project."
