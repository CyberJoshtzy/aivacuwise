"""AiVacuwise: entrance camera status.

The entrance camera program on the Raspberry Pi (entrance_client/recognize.py) calls
POST /camera/heartbeat every 15 seconds while it runs. The Live Evacuation page and the
Entrance Display read GET /camera/status to show "Camera on" or "Camera off", and TV Mode
uses stream_url to show the live webcam picture shared by the Pi.
Kept in memory only: after a server restart the status shows again within 15 seconds.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

import auth

router = APIRouter()

ONLINE_SECONDS = 45  # three missed heartbeats in a row = camera off
_last_seen: dict[tuple[int, str], dict] = {}


class Heartbeat(BaseModel):
    center_id: int
    kind: str = "entrance"
    stream_port: int | None = None


@router.post("/camera/heartbeat")
def camera_heartbeat(beat: Heartbeat, request: Request, user=Depends(auth.get_current_user)):
    host = request.client.host if request.client else None
    _last_seen[(beat.center_id, beat.kind)] = {
        "at": datetime.now(UTC),
        "host": host,
        "stream_port": beat.stream_port,
    }
    return {"ok": True}


@router.get("/camera/status")
def camera_status(user=Depends(auth.get_current_user)):
    now = datetime.now(UTC)
    rows = []
    for (center_id, kind), info in sorted(_last_seen.items()):
        port, host = info.get("stream_port"), info.get("host")
        rows.append(
            {
                "center_id": center_id,
                "kind": kind,
                "last_seen": info["at"].isoformat().replace("+00:00", "Z"),
                "online": (now - info["at"]).total_seconds() < ONLINE_SECONDS,
                "stream_url": "http://%s:%d/stream.mjpg" % (host, port) if host and port else None,
            }
        )
    return rows
