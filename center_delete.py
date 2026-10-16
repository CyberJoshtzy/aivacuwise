"""BilisLikas 2.0: delete an evacuation center together with its past records (after confirmation).

- GET    /evacuation_centers/{id}/usage   evacuees inside now and number of check-in records
- DELETE /evacuation_centers/{id}/force   removes the center and its check-in history
  (refused while evacuees are still inside)
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import auth
import models
from database import get_db

router = APIRouter()


def _role(u):
    return u.role.value if hasattr(u.role, "value") else u.role


def _inside(db, cid):
    C = models.CheckinRecord
    last = {}
    for r in db.query(C).filter(C.evacuation_center_id == cid).order_by(C.id).all():
        last[r.evacuee_id] = r.event_type
    n = 0
    for eid, ev in last.items():
        if ev != "check_in":
            continue
        latest = db.query(C).filter(C.evacuee_id == eid).order_by(C.id.desc()).first()
        if latest and latest.evacuation_center_id == cid and latest.event_type == "check_in":
            n += 1
    return n


def _check(cid, user, db):
    c = db.get(models.EvacuationCenter, cid)
    if not c:
        raise HTTPException(status_code=404, detail="Evacuation center not found.")
    if _role(user) != "city_admin" and user.barangay_id != c.barangay_id:
        raise HTTPException(
            status_code=403, detail="You can only view your own barangay's centers."
        )
    return c


def _check_admin(cid, user, db):
    c = _check(cid, user, db)
    import approvals

    if not approvals.is_it_admin(user):
        raise HTTPException(
            status_code=403,
            detail="Deleting an evacuation center needs approval. Send a delete request to the City Hall IT Administrator.",
        )
    return c


@router.get("/evacuation_centers/{cid}/usage")
def center_usage(cid: int, user=Depends(auth.get_current_user), db: Session = Depends(get_db)):
    _check(cid, user, db)
    n = (
        db.query(models.CheckinRecord)
        .filter(models.CheckinRecord.evacuation_center_id == cid)
        .count()
    )
    return {"inside": _inside(db, cid), "checkins": n}


@router.delete("/evacuation_centers/{cid}/force")
def center_force_delete(
    cid: int, user=Depends(auth.get_current_user), db: Session = Depends(get_db)
):
    c = _check_admin(cid, user, db)
    inside = _inside(db, cid)
    if inside:
        raise HTTPException(
            status_code=409,
            detail="There are still %d evacuees inside this center. Move them to another center first."
            % inside,
        )
    for r in (
        db.query(models.CheckinRecord)
        .filter(models.CheckinRecord.evacuation_center_id == cid)
        .all()
    ):
        db.delete(r)
    for r in (
        db.query(models.Transfer)
        .filter((models.Transfer.from_center_id == cid) | (models.Transfer.to_center_id == cid))
        .all()
    ):
        db.delete(r)
    for r in (
        db.query(models.TrackerPing).filter(models.TrackerPing.evacuation_center_id == cid).all()
    ):
        r.evacuation_center_id = None
    for r in db.query(models.Incident).filter(models.Incident.evacuation_center_id == cid).all():
        r.evacuation_center_id = None
    if hasattr(models, "ReliefRecord"):
        for r in (
            db.query(models.ReliefRecord)
            .filter(models.ReliefRecord.evacuation_center_id == cid)
            .all()
        ):
            r.evacuation_center_id = None
    db.flush()
    db.delete(c)
    db.commit()
    return {"ok": True}
