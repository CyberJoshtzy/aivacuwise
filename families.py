"""BilisLikas 2.0: family details for pre-registration.

- Adds three columns to existing databases (local server and cloud hub) on startup:
  evacuees.guardian_evacuee_id, evacuees.home_barangay, households.member_count.
- GET  /barangays/{barangay_id}/families   families with head, expected size, and members
- PUT  /households/{household_id}/size     set the expected number of family members
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

import auth
import models
from database import get_db

router = APIRouter()
INFANT_YEARS = 2

try:  # add the new columns if this database was created before them
    from database import engine as _engine
    if _engine.dialect.name == "postgresql":
        with _engine.begin() as conn:
            conn.execute(text("ALTER TABLE evacuees ADD COLUMN IF NOT EXISTS guardian_evacuee_id INTEGER REFERENCES evacuees(id)"))
            conn.execute(text("ALTER TABLE evacuees ADD COLUMN IF NOT EXISTS home_barangay VARCHAR"))
            conn.execute(text("ALTER TABLE households ADD COLUMN IF NOT EXISTS member_count INTEGER"))
            conn.execute(text("ALTER TABLE incidents ADD COLUMN IF NOT EXISTS finished BOOLEAN"))
            conn.execute(text("ALTER TABLE incidents ADD COLUMN IF NOT EXISTS active_seconds INTEGER"))
            conn.execute(text("ALTER TABLE incidents ADD COLUMN IF NOT EXISTS resumed_at TIMESTAMP"))
except Exception as exc:  # the app still starts; the error is shown in the server log
    print("families: could not add new columns:", exc)


class FamilySize(BaseModel):
    member_count: int


def _age(birthdate):
    try:
        y, m, d = [int(x) for x in str(birthdate)[:10].split("-")]
        t = datetime.utcnow()
        return t.year - y - ((t.month, t.day) < (m, d))
    except Exception:
        return None


def _can_edit(user, barangay_id):
    return user.role == "city_admin" or user.barangay_id == barangay_id


@router.get("/barangays/{barangay_id}/families")
def list_families(barangay_id: int, db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    if not _can_edit(user, barangay_id):
        raise HTTPException(status_code=403, detail="You can only view your own barangay's families.")
    out = []
    for h in db.query(models.Household).filter(models.Household.registered_barangay_id == barangay_id).order_by(models.Household.id).all():
        members = db.query(models.Evacuee).filter(models.Evacuee.household_id == h.id).order_by(models.Evacuee.id).all()
        head = next((m for m in members if m.is_head_of_family), members[0] if members else None)
        out.append({
            "id": h.id,
            "head_name": head.full_name if head else None,
            "member_count": h.member_count,
            "registered": len(members),
            "members": [{"id": m.id, "full_name": m.full_name, "age": _age(m.birthdate),
                         "is_infant": (_age(m.birthdate) is not None and _age(m.birthdate) < INFANT_YEARS),
                         "is_head_of_family": bool(m.is_head_of_family)} for m in members],
        })
    return out


@router.put("/households/{household_id}/size")
def set_family_size(household_id: int, payload: FamilySize, db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    h = db.query(models.Household).filter(models.Household.id == household_id).first()
    if not h:
        raise HTTPException(status_code=404, detail="Family not found.")
    if not _can_edit(user, h.registered_barangay_id):
        raise HTTPException(status_code=403, detail="You can only edit your own barangay's families.")
    if not 1 <= payload.member_count <= 20:
        raise HTTPException(status_code=422, detail="Number of family members must be from 1 to 20.")
    h.member_count = payload.member_count
    db.commit()
    return {"id": h.id, "member_count": h.member_count}


# ---------- trackers: assign at pre-registration, overview for the Trackers page ----------
class TrackerAssign(BaseModel):
    device_id: Optional[str] = None


@router.put("/evacuees/{evacuee_id}/tracker")
def assign_tracker(evacuee_id: int, payload: TrackerAssign, db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    e = db.query(models.Evacuee).filter(models.Evacuee.id == evacuee_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="Evacuee not found.")
    if not _can_edit(user, e.registered_barangay_id):
        raise HTTPException(status_code=403, detail="You can only assign trackers to your own barangay's residents.")
    dev = " ".join((payload.device_id or "").split())
    # release any tracker this evacuee had before
    db.query(models.Tracker).filter(models.Tracker.assigned_evacuee_id == e.id).update(
        {models.Tracker.assigned_evacuee_id: None}, synchronize_session=False)
    if not dev:
        db.commit()
        return {"evacuee_id": e.id, "tracker": None}
    t = db.query(models.Tracker).filter(models.Tracker.device_id == dev).first()
    if t is not None and t.assigned_evacuee_id not in (None, e.id):
        other = db.query(models.Evacuee).filter(models.Evacuee.id == t.assigned_evacuee_id).first()
        raise HTTPException(status_code=409, detail="Tracker %s is already given to %s." % (dev, other.full_name if other else "another evacuee"))
    if t is None:
        t = models.Tracker(device_id=dev, tracking_method="gps")
        db.add(t)
    t.assigned_evacuee_id = e.id
    db.commit()
    db.refresh(t)
    return {"evacuee_id": e.id, "tracker": {"id": t.id, "device_id": t.device_id}}


@router.get("/trackers/overview")
def trackers_overview(db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    out = []
    q = db.query(models.Tracker).filter(models.Tracker.assigned_evacuee_id.isnot(None))
    for t in q.all():
        e = db.query(models.Evacuee).filter(models.Evacuee.id == t.assigned_evacuee_id).first()
        if e is None or (user.role != "city_admin" and e.registered_barangay_id != user.barangay_id):
            continue
        p = (db.query(models.GpsPing).filter(models.GpsPing.tracker_id == t.id)
             .order_by(models.GpsPing.timestamp.desc(), models.GpsPing.id.desc()).first())
        last = (db.query(models.CheckinRecord).filter(models.CheckinRecord.evacuee_id == e.id)
                .order_by(models.CheckinRecord.id.desc()).first())
        center = None
        if last is not None and last.event_type == "check_in":
            c = db.query(models.EvacuationCenter).filter(models.EvacuationCenter.id == last.evacuation_center_id).first()
            center = c.name if c else None
        out.append({
            "tracker_id": t.id, "device_id": t.device_id, "battery": t.battery_level,
            "evacuee_id": e.id, "full_name": e.full_name,
            "latitude": p.latitude if p else None, "longitude": p.longitude if p else None,
            "timestamp": p.timestamp.isoformat() if p and p.timestamp else None,
            "source": p.source if p else None, "center": center,
        })
    return out
