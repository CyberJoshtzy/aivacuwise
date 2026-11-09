"""Ai-Vacuwise: evacuation history (City Admin).

- GET    /history/incidents            every past evacuation (paused or finished), newest first
- GET    /history/incidents/{id}       one evacuation with every activity during it
                                        (check-ins, check-outs, relief and medicine given)
- DELETE /history/incidents/{id}       remove one evacuation record from the history
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import auth
import models
from database import get_db

router = APIRouter()


def _role(u):
    return u.role.value if hasattr(u.role, "value") else u.role


def _admin(user):  # own barangay only for officials (view), everything for the City Admin
    pass


def _city(user):
    if _role(user) != "city_admin":
        raise HTTPException(
            status_code=403, detail="Only the City Admin can delete evacuation records."
        )


def _iso(dt):
    return dt.isoformat() + "Z" if dt else None


def _window_checkins(db, i):
    C, CR = models.EvacuationCenter, models.CheckinRecord
    centers = [c.id for c in db.query(C).filter(C.barangay_id == i.barangay_id).all()]
    end = i.ended_at or datetime.utcnow()
    if not centers:
        return []
    return (
        db.query(CR)
        .filter(
            CR.evacuation_center_id.in_(centers), CR.timestamp >= i.started_at, CR.timestamp <= end
        )
        .order_by(CR.timestamp)
        .all()
    )


def _summary(db, i, names):
    rows = _window_checkins(db, i)
    ins = [r for r in rows if r.event_type == "check_in"]
    return {
        "id": i.id,
        "barangay_id": i.barangay_id,
        "barangay": names.get(("b", i.barangay_id)),
        "evacuation_center_id": i.evacuation_center_id,
        "center": names.get(("c", i.evacuation_center_id)),
        "disaster_type": i.disaster_type,
        "started_at": _iso(i.started_at),
        "ended_at": _iso(i.ended_at),
        "finished": bool(getattr(i, "finished", False)),
        "active": i.ended_at is None,
        "checkins": len(ins),
        "evacuees": len({r.evacuee_id for r in ins}),
        "active_seconds": models.incident_active_seconds(i),
    }


def _names(db):
    n = {}
    for b in db.query(models.Barangay).all():
        n[("b", b.id)] = b.name
    for c in db.query(models.EvacuationCenter).all():
        n[("c", c.id)] = c.name
    return n


@router.get("/history/incidents")
def history_list(
    barangay_id: int | None = None,
    user=Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    _admin(user)
    I = models.Incident  # noqa: E741
    q = db.query(I).filter(I.ended_at.isnot(None))
    if _role(user) != "city_admin":
        q = q.filter(I.barangay_id == user.barangay_id)
    elif barangay_id:
        q = q.filter(I.barangay_id == barangay_id)
    names = _names(db)
    return [_summary(db, i, names) for i in q.order_by(I.started_at.desc()).all()]


@router.get("/history/incidents/{iid}")
def history_detail(iid: int, user=Depends(auth.get_current_user), db: Session = Depends(get_db)):
    _admin(user)
    i = db.get(models.Incident, iid)
    if not i:
        raise HTTPException(status_code=404, detail="Evacuation record not found.")
    if _role(user) != "city_admin" and i.barangay_id != user.barangay_id:
        raise HTTPException(status_code=403, detail="You can only view your own barangay.")
    names = _names(db)
    out = _summary(db, i, names)
    acts = []
    ev_cache = {}

    def ev(eid):
        if eid not in ev_cache:
            e = db.get(models.Evacuee, eid)
            ev_cache[eid] = e.full_name if e else "Removed resident"
        return ev_cache[eid]

    acts.append(
        {
            "time": _iso(i.started_at),
            "kind": "start",
            "text": "Evacuation started (" + (i.disaster_type or "-") + ")",
            "by": (
                db.get(models.User, i.started_by).full_name
                if i.started_by and db.get(models.User, i.started_by)
                else None
            ),
        }
    )
    for r in _window_checkins(db, i):
        acts.append(
            {
                "time": _iso(r.timestamp),
                "kind": r.event_type,
                "text": ev(r.evacuee_id)
                + (" checked in at " if r.event_type == "check_in" else " left ")
                + (names.get(("c", r.evacuation_center_id)) or "a center"),
            }
        )
    if hasattr(models, "ReliefRecord"):
        R = models.ReliefRecord
        end = i.ended_at or datetime.utcnow()
        for r in (
            db.query(R)
            .filter(R.barangay_id == i.barangay_id, R.given_at >= i.started_at, R.given_at <= end)
            .all()
        ):
            acts.append(
                {
                    "time": _iso(r.given_at),
                    "kind": "relief",
                    "text": "%s given: %s %s %s" % (r.category, ("%g" % r.quantity), r.unit, r.item)
                    + (
                        " at " + names.get(("c", r.evacuation_center_id))
                        if r.evacuation_center_id and names.get(("c", r.evacuation_center_id))
                        else ""
                    )
                    + (", %d persons served" % r.recipients if r.recipients else ""),
                }
            )
    if i.ended_at:
        acts.append(
            {
                "time": _iso(i.ended_at),
                "kind": "end",
                "text": "Evacuation " + ("finished" if getattr(i, "finished", False) else "paused"),
                "by": (
                    db.get(models.User, i.ended_by).full_name
                    if i.ended_by and db.get(models.User, i.ended_by)
                    else None
                ),
            }
        )
    acts.sort(key=lambda a: a["time"] or "")
    out["activities"] = acts
    out["checkouts"] = len([a for a in acts if a["kind"] == "check_out"])
    out["relief"] = len([a for a in acts if a["kind"] == "relief"])
    return out


@router.delete("/history/incidents/{iid}")
def history_delete(iid: int, user=Depends(auth.get_current_user), db: Session = Depends(get_db)):
    _city(user)
    i = db.get(models.Incident, iid)
    if not i:
        raise HTTPException(status_code=404, detail="Evacuation record not found.")
    if i.ended_at is None:
        raise HTTPException(
            status_code=409, detail="This evacuation is still running. Finish it first."
        )
    db.delete(i)
    db.commit()
    return {"ok": True}


@router.get("/history/center/{cid}")
def history_center(cid: int, user=Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Past activity at one evacuation center: each finished evacuation that used it, and its latest check-ins."""
    _admin(user)
    c = db.get(models.EvacuationCenter, cid)
    if not c:
        raise HTTPException(status_code=404, detail="Evacuation center not found.")
    if _role(user) != "city_admin" and c.barangay_id != user.barangay_id:
        raise HTTPException(status_code=403, detail="You can only view your own barangay.")
    I, CR = models.Incident, models.CheckinRecord  # noqa: E741
    evacs = []
    for i in (
        db.query(I)
        .filter(I.barangay_id == c.barangay_id, I.ended_at.isnot(None))
        .order_by(I.started_at.desc())
        .all()
    ):
        if not getattr(i, "finished", False):
            continue
        rows = [
            r
            for r in _window_checkins(db, i)
            if r.evacuation_center_id == cid and r.event_type == "check_in"
        ]
        evacs.append(
            {
                "id": i.id,
                "disaster_type": i.disaster_type,
                "started_at": _iso(i.started_at),
                "ended_at": _iso(i.ended_at),
                "active_seconds": models.incident_active_seconds(i),
                "evacuees": len({r.evacuee_id for r in rows}),
            }
        )
    recent = []
    for r in (
        db.query(CR)
        .filter(CR.evacuation_center_id == cid)
        .order_by(CR.timestamp.desc())
        .limit(30)
        .all()
    ):
        e = db.get(models.Evacuee, r.evacuee_id)
        recent.append(
            {
                "time": _iso(r.timestamp),
                "kind": r.event_type,
                "name": e.full_name if e else "Removed resident",
            }
        )
    return {
        "id": c.id,
        "name": c.name,
        "address": c.address,
        "capacity": c.capacity,
        "evacuations": evacs,
        "recent": recent,
    }
