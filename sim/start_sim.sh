#!/usr/bin/env bash
# Starts the sync simulation: Server B (8001), the cloud hub (9000), and the sync agents for A and B.
# Server A (8000) is your normal systemd service and is not restarted.
set -e
cd "$(dirname "$0")/.."
mkdir -p sim/logs data
if ! grep -q "^SYNC_KEY=" .env; then echo "STOP: SYNC_KEY is missing from .env (see the installation steps)."; exit 1; fi
echo "Starting the two simulation databases..."
docker compose -p bilislikas_sim -f sim/docker-compose.sim.yml up -d
for c in bilislikas_postgres_b bilislikas_postgres_hub; do
  for i in $(seq 1 40); do docker exec "$c" pg_isready -q >/dev/null 2>&1 && break; sleep 1; done
done

start_node () {
  name=$1; port=$2; dbport=$3
  if pgrep -f "uvicorn main:app --host 127.0.0.1 --port $port" >/dev/null; then
    echo "  $name is already running on port $port"; return
  fi
  POSTGRES_PORT=$dbport BILISLIKAS_SERVER_ID=$name BL_PHOTO_DIR=data/photos_$name ./venv/bin/python sim/init_db.py
  POSTGRES_PORT=$dbport BILISLIKAS_SERVER_ID=$name BL_PHOTO_DIR=data/photos_$name \
    nohup ./venv/bin/uvicorn main:app --host 127.0.0.1 --port "$port" > "sim/logs/$name.log" 2>&1 &
  echo "  $name started: http://127.0.0.1:$port"
}

start_agent () {
  name=$1; port=$2; dbport=$3
  if pgrep -f "sync_agent.py $name" >/dev/null; then echo "  sync agent for $name is already running"; return; fi
  POSTGRES_PORT=$dbport BILISLIKAS_SERVER_ID=$name LOCAL_URL=http://127.0.0.1:$port HUB_URL=http://127.0.0.1:9000 SYNC_INTERVAL=15 \
    nohup ./venv/bin/python sync_agent.py "$name" > "sim/logs/agent-$name.log" 2>&1 &
  echo "  sync agent for $name started (log: sim/logs/agent-$name.log)"
}

echo "Starting the backends..."
start_node server-b 8001 5433
start_node cloud-hub 9000 5434
sleep 4
echo "Starting the sync agents (every 15 seconds)..."
start_agent server-a 8000 5432
start_agent server-b 8001 5433
echo "Checking all three servers:"
for p in 8000 8001 9000; do
  printf "  port %s: " "$p"; curl -s -m 3 "http://127.0.0.1:$p/" || printf "not answering (check sim/logs)"; echo
done
echo "Watch syncing live with:  tail -f sim/logs/agent-server-a.log sim/logs/agent-server-b.log"
