#!/usr/bin/env bash
# Stops the sync agents, Server B, the cloud hub and their databases. Data is kept for next time.
cd "$(dirname "$0")/.."
pkill -f "sync_agent.py server-a" && echo "Sync agent A stopped" || true
pkill -f "sync_agent.py server-b" && echo "Sync agent B stopped" || true
pkill -f "uvicorn main:app --host 127.0.0.1 --port 8001" && echo "Server B stopped" || echo "Server B was not running"
pkill -f "uvicorn main:app --host 127.0.0.1 --port 9000" && echo "Cloud hub stopped" || echo "Cloud hub was not running"
docker compose -p bilislikas_sim -f sim/docker-compose.sim.yml stop
echo "Simulation stopped. Server A (port 8000) is still running."
