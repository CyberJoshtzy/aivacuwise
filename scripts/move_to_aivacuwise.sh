#!/usr/bin/env bash
# Renames the project on the laptop server from "ai-vacuwise" to "aivacuwise".
#
# Run from your home folder (not from inside the project):
#     cd ~ && bash ~/ai-vacuwise/scripts/move_to_aivacuwise.sh
#
# What it does:
#   1. Checks that the database volume exists, so no data is lost.
#   2. Stops the backend service "bilislikas" (and the sync agent if installed).
#   3. Moves ~/ai-vacuwise to ~/aivacuwise and leaves shortcuts (symlinks) at
#      ~/ai-vacuwise and ~/bilislikas2.0, so the venv and old commands keep working.
#   4. Replaces the service "bilislikas" with "aivacuwise" (same settings, new folder),
#      and "bilislikas-sync" with "aivacuwise-sync" if it exists.
#   5. Starts the backend again and checks that it answers.
# The Docker database keeps running the whole time; its data is not touched.

set -e
OLD="$HOME/ai-vacuwise"
NEW="$HOME/aivacuwise"
OLDEST="$HOME/bilislikas2.0"
ME="$(id -un)"

echo "== AiVacuwise rename (laptop) =="

if [ -d "$NEW" ] && [ ! -L "$NEW" ] && [ -L "$OLD" ]; then
  echo "Already done: $OLD is a shortcut to $(readlink "$OLD")."
  exit 0
fi
if [ ! -d "$OLD" ] || [ -L "$OLD" ]; then
  echo "Stopped: the folder $OLD was not found."
  exit 1
fi
if [ -e "$NEW" ]; then
  echo "Stopped: $NEW already exists. Rename or remove it first."
  exit 1
fi
case "$PWD/" in
  "$OLD"/*|"$OLDEST"/*) echo "Stopped: run this from your home folder:  cd ~ && bash $OLD/scripts/move_to_aivacuwise.sh"; exit 1 ;;
esac

# 1. Database volume check
if ! docker volume ls --format '{{.Name}}' | grep -qx 'bilislikas20_postgres_data'; then
  echo "Stopped: Docker volume 'bilislikas20_postgres_data' was not found."
  docker volume ls
  echo "Send this list to Claude before renaming."
  exit 1
fi
grep -q '^name: bilislikas20' "$OLD/docker-compose.yml" || { echo "Stopped: docker-compose.yml lost its fixed project name."; exit 1; }
echo "OK  database volume found; the database keeps its data"

# sudo password (typed visibly, because hidden password prompts do not work on this laptop)
if ! sudo -n true 2>/dev/null; then
  read -r -p "Laptop password for sudo (it will show on screen): " PW
  echo "$PW" | sudo -S -v 2>/dev/null || { echo "Stopped: wrong password."; exit 1; }
  unset PW
fi

# 2. Stop services
sudo systemctl stop bilislikas 2>/dev/null || true
SYNC=0
if [ -f /etc/systemd/system/bilislikas-sync.service ]; then
  SYNC=1
  sudo systemctl stop bilislikas-sync || true
fi
echo "OK  services stopped"

# 3. Move the folder; keep shortcuts at the old paths
mv "$OLD" "$NEW"
ln -s "$NEW" "$OLD"
if [ -L "$OLDEST" ]; then
  ln -sfn "$NEW" "$OLDEST"
fi
echo "OK  moved to $NEW (shortcuts left at $OLD and $OLDEST)"

# 4. New service names, pointing at the new folder
if [ -f /etc/systemd/system/bilislikas.service ]; then
  sed -e "s#/home/$ME/ai-vacuwise#/home/$ME/aivacuwise#g" -e "s#/home/$ME/bilislikas2\.0#/home/$ME/aivacuwise#g" \
      -e "s#^Description=.*#Description=AiVacuwise backend (FastAPI)#" \
      /etc/systemd/system/bilislikas.service | sudo tee /etc/systemd/system/aivacuwise.service >/dev/null
  sudo systemctl disable bilislikas >/dev/null 2>&1 || true
  sudo rm -f /etc/systemd/system/bilislikas.service
  echo "OK  service bilislikas replaced by aivacuwise"
fi
if [ "$SYNC" = 1 ]; then
  sudo cp "$NEW/deploy/aivacuwise-sync.service" /etc/systemd/system/aivacuwise-sync.service
  sudo systemctl disable bilislikas-sync >/dev/null 2>&1 || true
  sudo rm -f /etc/systemd/system/bilislikas-sync.service
  echo "OK  service bilislikas-sync replaced by aivacuwise-sync"
fi
sudo systemctl daemon-reload
sudo systemctl enable aivacuwise >/dev/null 2>&1
sudo systemctl start aivacuwise
if [ "$SYNC" = 1 ]; then
  sudo systemctl enable aivacuwise-sync >/dev/null 2>&1
  sudo systemctl start aivacuwise-sync
fi
echo "OK  services started"

# 5. Check
sleep 10
echo "Server says: $(curl -s http://127.0.0.1:8000 || echo 'not responding')"
echo
echo "Done. From now on:"
echo "  Project folder:   cd ~/aivacuwise && source venv/bin/activate"
echo "  Restart server:   sudo systemctl restart aivacuwise"
echo "  Server logs:      journalctl -u aivacuwise -f"
echo "In VS Code: File > Open Folder > aivacuwise"
