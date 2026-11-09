"""Ai-Vacuwise: delete a barangay together with everything registered under it (after confirmation).

- GET    /barangays/{id}/usage   counts of centers, residents, accounts, households, evacuation records
- DELETE /barangays/{id}/force   City Admin only; refused while an evacuation is running there
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import auth
import models
from database import get_db

router = APIRouter()


def _role(u):
    return u.role.value if hasattr(u.role, "value") else u.role


def _admin(user):
    if _role(user) != "city_admin":
        raise HTTPException(status_code=403, detail="Only the City Admin can delete a barangay.")


@router.get("/barangays/{bid}/usage")
def barangay_usage(bid: int, user=Depends(auth.get_current_user), db: Session = Depends(get_db)):
    _admin(user)
    if not db.get(models.Barangay, bid):
        raise HTTPException(status_code=404, detail="Barangay not found.")
    I = models.Incident  # noqa: E741
    return {
        "centers": db.query(models.EvacuationCenter)
        .filter(models.EvacuationCenter.barangay_id == bid)
        .count(),
        "residents": db.query(models.Evacuee)
        .filter(models.Evacuee.registered_barangay_id == bid)
        .count(),
        "accounts": db.query(models.User).filter(models.User.barangay_id == bid).count(),
        "households": db.query(models.Household)
        .filter(models.Household.registered_barangay_id == bid)
        .count(),
        "evacuations": db.query(I).filter(I.barangay_id == bid).count(),
        "active": db.query(I).filter(I.barangay_id == bid, I.ended_at.is_(None)).count(),
    }


@router.delete("/barangays/{bid}/force")
def barangay_force_delete(
    bid: int, user=Depends(auth.get_current_user), db: Session = Depends(get_db)
):
    _admin(user)
    b = db.get(models.Barangay, bid)
    if not b:
        raise HTTPException(status_code=404, detail="Barangay not found.")
    I, E, C, H, U, CR = (  # noqa: E741
        models.Incident,
        models.Evacuee,
        models.EvacuationCenter,
        models.Household,
        models.User,
        models.CheckinRecord,
    )
    if db.query(I).filter(I.barangay_id == bid, I.ended_at.is_(None)).count():
        raise HTTPException(
            status_code=409,
            detail="An evacuation is still running in this barangay. Finish it first.",
        )
    center_ids = [c.id for c in db.query(C).filter(C.barangay_id == bid).all()]
    ev_ids = [e.id for e in db.query(E).filter(E.registered_barangay_id == bid).all()]
    if hasattr(models, "ReliefRecord"):
        for r in db.query(models.ReliefRecord).filter(models.ReliefRecord.barangay_id == bid).all():
            db.delete(r)
    for r in (
        db.query(CR)
        .filter((CR.evacuee_id.in_(ev_ids)) | (CR.evacuation_center_id.in_(center_ids)))
        .all()
    ):
        db.delete(r)
    for r in (
        db.query(models.Transfer)
        .filter(
            (models.Transfer.evacuee_id.in_(ev_ids))
            | (models.Transfer.from_center_id.in_(center_ids))
            | (models.Transfer.to_center_id.in_(center_ids))
        )
        .all()
    ):
        db.delete(r)
    for t in db.query(models.Tracker).filter(models.Tracker.assigned_evacuee_id.in_(ev_ids)).all():
        t.assigned_evacuee_id = None
    for p in (
        db.query(models.TrackerPing)
        .filter(models.TrackerPing.evacuation_center_id.in_(center_ids))
        .all()
    ):
        p.evacuation_center_id = None
    for r in db.query(I).filter(I.barangay_id == bid).all():
        db.delete(r)
    for h in db.query(H).filter(H.registered_barangay_id == bid).all():
        h.head_of_family_evacuee_id = None
    for e in db.query(E).filter(E.id.in_(ev_ids)).all():
        if hasattr(e, "guardian_evacuee_id"):
            e.guardian_evacuee_id = None
        e.household_id = None
    for e in (
        db.query(E)
        .filter(getattr(E, "guardian_evacuee_id", E.id).in_(ev_ids), ~E.id.in_(ev_ids))
        .all()
        if hasattr(E, "guardian_evacuee_id")
        else []
    ):
        e.guardian_evacuee_id = None
    db.flush()
    for e in db.query(E).filter(E.id.in_(ev_ids)).all():
        db.delete(e)
    for h in db.query(H).filter(H.registered_barangay_id == bid).all():
        db.delete(h)
    for u in db.query(U).filter(U.barangay_id == bid).all():
        db.delete(u)
    for c in db.query(C).filter(C.id.in_(center_ids)).all():
        db.delete(c)
    db.flush()
    db.delete(b)
    db.commit()
    return {"ok": True}
