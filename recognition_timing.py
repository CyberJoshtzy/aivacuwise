"""Ai-Vacuwise: how fast the entrance camera recognizes and checks in each evacuee.

The entrance camera program on the Raspberry Pi (entrance_client/recognize.py) measures,
for every automatic check-in or transfer, three moments on the Pi's own clock:
    1. face seen     first camera frame in which a face was detected
    2. recognized    that face was matched to an enrolled evacuee
    3. saved         the laptop server confirmed the check-in
and sends them here. All durations are measured on one clock (the Pi), so a time
difference between the Pi and the laptop cannot distort them.

- Table recognition_timings (created on startup)
- POST /recognition/timings                 the Pi reports one measurement
- GET  /recognition/timings/latest?center_id=   newest measurement per evacuee (Entrance Display)
- GET  /recognition/timings.csv             every measurement as a CSV file for Excel (Chapter 4)
"""

import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    insert,
    select,
)
from sqlalchemy.orm import Session

import auth
import models
from database import engine, get_db

router = APIRouter()
_meta = MetaData()
timings = Table(
    "recognition_timings",
    _meta,
    Column("id", Integer, primary_key=True),
    Column("created_at", DateTime, nullable=False, index=True),  # laptop clock, when stored
    Column("evacuee_id", Integer, nullable=False, index=True),
    Column("center_id", Integer, nullable=False, index=True),
    Column("action", String, nullable=False),  # check_in or transfer
    Column("record_id", Integer, nullable=True),
    Column("face_seen_at", DateTime, nullable=True),  # Pi clock (UTC)
    Column("recognized_at", DateTime, nullable=True),
    Column("saved_at", DateTime, nullable=True),
    Column("recognition_s", Float, nullable=True),  # face seen -> recognized
    Column("frame_ms", Float, nullable=True),  # processing time of the matching frame
    Column("save_s", Float, nullable=True),  # recognized -> saved
    Column("total_s", Float, nullable=True),  # face seen -> saved
    Column("distance", Float, nullable=True),
    Column("width", Integer, nullable=True),
    Column("height", Integer, nullable=True),
    Column("frame_scale", Float, nullable=True),
)
try:
    _meta.create_all(engine)
except Exception as exc:
    print("recognition_timing: could not create table:", exc)


class TimingIn(BaseModel):
    evacuee_id: int
    center_id: int
    action: str = "check_in"
    record_id: int | None = None
    face_seen_at: float | None = None  # Unix seconds on the Pi
    recognized_at: float | None = None
    saved_at: float | None = None
    frame_ms: float | None = None
    distance: float | None = None
    width: int | None = None
    height: int | None = None
    frame_scale: float | None = None


def _dt(x):
    return datetime.utcfromtimestamp(x) if x else None


def _diff(a, b):
    return round(b - a, 3) if a and b and b >= a else None


def _allowed_centers(db, user):
    q = db.query(models.EvacuationCenter.id)
    if user.role != "city_admin":
        q = q.filter(models.EvacuationCenter.barangay_id == user.barangay_id)
    return {r[0] for r in q.all()}


@router.post("/recognition/timings")
def add_timing(t: TimingIn, db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    if t.action not in ("check_in", "transfer"):
        raise HTTPException(status_code=422, detail="action must be check_in or transfer")
    row = {
        "created_at": datetime.utcnow(),
        "evacuee_id": t.evacuee_id,
        "center_id": t.center_id,
        "action": t.action,
        "record_id": t.record_id,
        "face_seen_at": _dt(t.face_seen_at),
        "recognized_at": _dt(t.recognized_at),
        "saved_at": _dt(t.saved_at),
        "recognition_s": _diff(t.face_seen_at, t.recognized_at),
        "frame_ms": round(t.frame_ms, 1) if t.frame_ms is not None else None,
        "save_s": _diff(t.recognized_at, t.saved_at),
        "total_s": _diff(t.face_seen_at, t.saved_at),
        "distance": round(t.distance, 4) if t.distance is not None else None,
        "width": t.width,
        "height": t.height,
        "frame_scale": t.frame_scale,
    }
    db.execute(insert(timings).values(**row))
    db.commit()
    return {"ok": True, "recognition_s": row["recognition_s"], "total_s": row["total_s"]}


def _iso(d):
    return d.isoformat() if d else None


def _row_dict(r):
    return {
        "evacuee_id": r.evacuee_id,
        "center_id": r.center_id,
        "action": r.action,
        "created_at": _iso(r.created_at),
        "recognition_s": r.recognition_s,
        "frame_ms": r.frame_ms,
        "save_s": r.save_s,
        "total_s": r.total_s,
        "distance": r.distance,
        "width": r.width,
        "height": r.height,
    }


@router.get("/recognition/timings/latest")
def latest_timings(center_id: int, db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    if center_id not in _allowed_centers(db, user):
        raise HTTPException(status_code=403, detail="Not your evacuation center.")
    rows = db.execute(
        select(timings)
        .where(timings.c.center_id == center_id)
        .order_by(timings.c.id.desc())
        .limit(300)
    ).all()
    out = {}
    for r in rows:
        out.setdefault(str(r.evacuee_id), _row_dict(r))
    return out


@router.get("/recognition/timings.csv")
def timings_csv(db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    allowed = _allowed_centers(db, user)
    rows = db.execute(select(timings).order_by(timings.c.id)).all()
    names = {e.id: e.full_name for e in db.query(models.Evacuee).all()}
    centers = {c.id: c.name for c in db.query(models.EvacuationCenter).all()}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "No.",
            "Date",
            "Evacuee",
            "Evacuation center",
            "Action",
            "Face seen (Pi time, UTC)",
            "Recognized (Pi time, UTC)",
            "Saved (Pi time, UTC)",
            "Recognition time (s)",
            "Processing time of matching frame (ms)",
            "Saving time (s)",
            "Total time (s)",
            "Match distance (lower = closer match)",
            "Camera resolution",
            "Frame scale",
        ]
    )
    n = 0
    fmt = lambda d: d.strftime("%H:%M:%S.%f")[:-3] if d else ""  # noqa: E731
    for r in rows:
        if r.center_id not in allowed:
            continue
        n += 1
        w.writerow(
            [
                n,
                r.created_at.strftime("%Y-%m-%d") if r.created_at else "",
                names.get(r.evacuee_id, "Evacuee #%s" % r.evacuee_id),
                centers.get(r.center_id, "Center #%s" % r.center_id),
                "Check-in" if r.action == "check_in" else "Transfer",
                fmt(r.face_seen_at),
                fmt(r.recognized_at),
                fmt(r.saved_at),
                r.recognition_s,
                r.frame_ms,
                r.save_s,
                r.total_s,
                r.distance,
                "%sx%s" % (r.width, r.height) if r.width and r.height else "",
                r.frame_scale,
            ]
        )
    data = "﻿" + buf.getvalue()  # BOM so Excel opens it as UTF-8
    return StreamingResponse(
        iter([data]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="recognition_times.csv"'},
    )
