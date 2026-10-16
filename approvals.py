"""BilisLikas 2.0: approvals handled by the City Hall IT Administrator (System Administrator account).

1. Barangay official sign-up starts as "pending". The barangay and evacuation centers typed in the sign-up
   form are remembered here; if the request is rejected, anything that sign-up created is removed again.
2. Barangay officials cannot add, edit or delete evacuation centers directly. They send a change request,
   and the IT Administrator approves or rejects it.

- POST /center-requests                    barangay official: {center_id, action: edit|delete, name, address, capacity, reason}
- GET  /center-requests?status=pending     IT admin: all; official: own barangay
- POST /center-requests/{id}/approve       IT admin only
- POST /center-requests/{id}/reject        IT admin only, {note}
- GET  /admin/signup-info                  IT admin: what each pending barangay sign-up added
"""

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.orm import Session

import auth
import models
from database import Base, get_db

router = APIRouter()


class SignupRecord(Base):
    __tablename__ = "signup_records"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    barangay_id = Column(Integer, nullable=True)
    new_barangay = Column(Boolean, nullable=False, default=False)
    center_ids = Column(Text, nullable=True)  # JSON list
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class CenterRequest(Base):
    __tablename__ = "center_change_requests"
    id = Column(Integer, primary_key=True)
    center_id = Column(Integer, nullable=False, index=True)
    barangay_id = Column(Integer, nullable=True, index=True)
    action = Column(String, nullable=False)  # edit or delete
    payload = Column(Text, nullable=True)  # JSON of the new values
    reason = Column(String, nullable=True)
    status = Column(
        String, nullable=False, default="pending", index=True
    )  # pending, approved, rejected
    requested_by = Column(Integer, nullable=True)
    reviewed_by = Column(Integer, nullable=True)
    review_note = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)


try:
    from database import engine as _engine

    SignupRecord.__table__.create(_engine, checkfirst=True)
    CenterRequest.__table__.create(_engine, checkfirst=True)
except Exception as exc:
    print("approvals: could not create tables:", exc)


def _role(u):
    return u.role.value if hasattr(u.role, "value") else u.role


import os as _os

IT_ADMIN_EMAIL = (_os.environ.get("IT_ADMIN_EMAIL") or "itadmin@bilislikas.local").strip().lower()


def is_it_admin(u):
    """Only the City Hall IT Administrator account approves accounts and barangay requests."""
    email = (getattr(u, "email", None) or getattr(u, "username", "") or "").strip().lower()
    return (
        _role(u) == "city_admin"
        and bool(getattr(u, "is_superuser", False))
        and email == IT_ADMIN_EMAIL
    )


def require_it_admin(user=Depends(auth.get_current_user)):
    if not is_it_admin(user):
        raise HTTPException(
            status_code=403, detail="Only the City Hall IT Administrator can do this."
        )
    return user


# ---------- barangay sign-up ----------
def remember_signup(db, user_id, barangay_id, new_barangay, center_ids):
    db.add(
        SignupRecord(
            user_id=user_id,
            barangay_id=barangay_id,
            new_barangay=bool(new_barangay),
            center_ids=json.dumps(list(center_ids or [])),
        )
    )


def undo_signup(db, user):
    """Called when a pending barangay sign-up is rejected: remove the centers and the new barangay it created,
    as long as nothing else uses them yet."""
    rec = (
        db.query(SignupRecord)
        .filter(SignupRecord.user_id == user.id)
        .order_by(SignupRecord.id.desc())
        .first()
    )
    if not rec:
        return
    C, CK = models.EvacuationCenter, models.CheckinRecord
    for cid in json.loads(rec.center_ids or "[]"):
        c = db.get(C, cid)
        if c and not db.query(CK).filter(CK.evacuation_center_id == cid).first():
            db.delete(c)
    db.flush()
    if rec.new_barangay and rec.barangay_id:
        b = db.get(models.Barangay, rec.barangay_id)
        others = (
            db.query(models.User)
            .filter(models.User.barangay_id == rec.barangay_id, models.User.id != user.id)
            .first()
        )
        residents = (
            db.query(models.Evacuee)
            .filter(models.Evacuee.registered_barangay_id == rec.barangay_id)
            .first()
        )
        centers = db.query(C).filter(C.barangay_id == rec.barangay_id).first()
        if b and not others and not residents and not centers:
            user.barangay_id = None
            db.flush()
            db.delete(b)
    db.delete(rec)


@router.get("/admin/signup-info")
def signup_info(me=Depends(require_it_admin), db: Session = Depends(get_db)):
    out = {}
    for r in db.query(SignupRecord).all():
        names = []
        for cid in json.loads(r.center_ids or "[]"):
            c = db.get(models.EvacuationCenter, cid)
            if c:
                names.append(c.name)
        out[r.user_id] = {"new_barangay": bool(r.new_barangay), "centers": names}
    return out


# ---------- evacuation center change requests ----------
class CenterReq(BaseModel):
    center_id: int
    action: str
    name: str | None = None
    address: str | None = None
    capacity: int | None = None
    reason: str | None = None


def _req_dict(r, db):
    c = db.get(models.EvacuationCenter, r.center_id)
    b = db.get(models.Barangay, r.barangay_id) if r.barangay_id else None
    by = db.get(models.User, r.requested_by) if r.requested_by else None
    rv = db.get(models.User, r.reviewed_by) if r.reviewed_by else None
    return {
        "id": r.id,
        "center_id": r.center_id,
        "center": c.name if c else "(deleted center)",
        "current": {"name": c.name, "address": c.address, "capacity": c.capacity} if c else None,
        "barangay_id": r.barangay_id,
        "barangay": b.name if b else None,
        "action": r.action,
        "changes": json.loads(r.payload or "{}"),
        "reason": r.reason,
        "status": r.status,
        "requested_by": by.full_name if by else None,
        "reviewed_by": rv.full_name if rv else None,
        "review_note": r.review_note,
        "created_at": r.created_at.isoformat() + "Z",
        "reviewed_at": r.reviewed_at.isoformat() + "Z" if r.reviewed_at else None,
    }


@router.post("/center-requests", status_code=201)
def create_request(
    p: CenterReq, user=Depends(auth.get_current_user), db: Session = Depends(get_db)
):
    c = db.get(models.EvacuationCenter, p.center_id)
    if not c:
        raise HTTPException(status_code=404, detail="Evacuation center not found.")
    if _role(user) != "city_admin" and user.barangay_id != c.barangay_id:
        raise HTTPException(
            status_code=403, detail="You can only request changes for your own barangay's centers."
        )
    if p.action not in ("edit", "delete"):
        raise HTTPException(status_code=422, detail="Action must be edit or delete.")
    if (
        db.query(CenterRequest)
        .filter(CenterRequest.center_id == c.id, CenterRequest.status == "pending")
        .first()
    ):
        raise HTTPException(
            status_code=409, detail="This center already has a request waiting for approval."
        )
    changes = {}
    if p.action == "edit":
        if p.name is not None and " ".join(p.name.split()) and " ".join(p.name.split()) != c.name:
            changes["name"] = " ".join(p.name.split())
        if p.address is not None and " ".join(p.address.split()) != (c.address or ""):
            changes["address"] = " ".join(p.address.split())
        if p.capacity is not None:
            if p.capacity < 1:
                raise HTTPException(status_code=422, detail="Capacity must be at least 1.")
            if p.capacity != c.capacity:
                changes["capacity"] = int(p.capacity)
        if not changes:
            raise HTTPException(status_code=422, detail="Nothing was changed.")
    r = CenterRequest(
        center_id=c.id,
        barangay_id=c.barangay_id,
        action=p.action,
        payload=json.dumps(changes),
        reason=" ".join((p.reason or "").split())[:300] or None,
        requested_by=user.id,
    )
    db.add(r)
    db.commit()
    return _req_dict(r, db)


@router.get("/center-requests")
def list_requests(
    status: str | None = None, user=Depends(auth.get_current_user), db: Session = Depends(get_db)
):
    q = db.query(CenterRequest)
    if not is_it_admin(user):
        if _role(user) == "city_admin":
            pass
        else:
            q = q.filter(CenterRequest.barangay_id == user.barangay_id)
    if status:
        q = q.filter(CenterRequest.status == status)
    return [_req_dict(r, db) for r in q.order_by(CenterRequest.id.desc()).limit(200).all()]


class Review(BaseModel):
    note: str | None = None


@router.post("/center-requests/{rid}/approve")
def approve_request(rid: int, me=Depends(require_it_admin), db: Session = Depends(get_db)):
    r = db.get(CenterRequest, rid)
    if not r or r.status != "pending":
        raise HTTPException(status_code=404, detail="No pending request with this number.")
    c = db.get(models.EvacuationCenter, r.center_id)
    import center_delete

    if c is None:
        r.status = "rejected"
        r.review_note = "The center no longer exists."
    elif r.action == "edit":
        ch = json.loads(r.payload or "{}")
        if "capacity" in ch and ch["capacity"] < center_delete._inside(db, c.id):
            raise HTTPException(
                status_code=409,
                detail="The new capacity is lower than the number of evacuees inside right now.",
            )
        for k, v in ch.items():
            setattr(c, k, v)
        r.status = "approved"
    else:
        if center_delete._inside(db, c.id):
            raise HTTPException(
                status_code=409,
                detail="Evacuees are still inside this center. It can be deleted once they leave.",
            )
        r.status = "approved"
        r.reviewed_by, r.reviewed_at = me.id, datetime.utcnow()
        db.commit()
        center_delete.center_force_delete(
            c.id, me, db
        )  # removes the center and its records, then commits
        return _req_dict(r, db)
    r.reviewed_by, r.reviewed_at = me.id, datetime.utcnow()
    db.commit()
    return _req_dict(r, db)


@router.post("/center-requests/{rid}/reject")
def reject_request(
    rid: int, p: Review | None = None, me=Depends(require_it_admin), db: Session = Depends(get_db)
):
    r = db.get(CenterRequest, rid)
    if not r or r.status != "pending":
        raise HTTPException(status_code=404, detail="No pending request with this number.")
    r.status, r.reviewed_by, r.reviewed_at = "rejected", me.id, datetime.utcnow()
    r.review_note = " ".join(((p.note if p else "") or "").split())[:300] or None
    db.commit()
    return _req_dict(r, db)
