#!/usr/bin/env bash
# Applies the phase 3 database changes to Server B's and the hub's databases.
cd "$(dirname "$0")/.."
pkill -f "sync_agent.py" || true
pkill -f "uvicorn main:app --host 127.0.0.1 --port 8001" || true
pkill -f "uvicorn main:app --host 127.0.0.1 --port 9000" || true
sleep 2
docker compose -p bilislikas_sim -f sim/docker-compose.sim.yml up -d
for c in bilislikas_postgres_b bilislikas_postgres_hub; do
  for i in $(seq 1 40); do docker exec "$c" pg_isready -q >/dev/null 2>&1 && break; sleep 1; done
done
POSTGRES_PORT=5433 BILISLIKAS_SERVER_ID=server-b ./venv/bin/python migrate_sync_phase3.py
POSTGRES_PORT=5434 BILISLIKAS_SERVER_ID=cloud-hub ./venv/bin/python migrate_sync_phase3.py
echo "Now start everything again with:  ./sim/start_sim.sh"
