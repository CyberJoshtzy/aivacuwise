"""Ai-Vacuwise: entrance camera status.

The entrance camera program on the Raspberry Pi (entrance_client/recognize.py) calls
POST /camera/heartbeat every 15 seconds while it runs. The Live Evacuation page and the
Entrance Display read GET /camera/status to show "Camera on" or "Camera off".
Kept in memory only: after a server restart the status shows again within 15 seconds.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

import auth

router = APIRouter()

ONLINE_SECONDS = 45  # three missed heartbeats in a row = camera off
_last_seen: dict[tuple[int, str], datetime] = {}


class Heartbeat(BaseModel):
    center_id: int
    kind: str = "entrance"


@router.post("/camera/heartbeat")
def camera_heartbeat(beat: Heartbeat, user=Depends(auth.get_current_user)):
    _last_seen[(beat.center_id, beat.kind)] = datetime.now(UTC)
    return {"ok": True}


@router.get("/camera/status")
def camera_status(user=Depends(auth.get_current_user)):
    now = datetime.now(UTC)
    return [
        {
            "center_id": center_id,
            "kind": kind,
            "last_seen": seen.isoformat().replace("+00:00", "Z"),
            "online": (now - seen).total_seconds() < ONLINE_SECONDS,
        }
        for (center_id, kind), seen in sorted(_last_seen.items())
    ]
