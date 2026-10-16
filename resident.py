"""BilisLikas 2.0: resident / evacuee portal (read-only, own family only).

Residents do not sign up. They were pre-registered by their barangay, so they sign in with
  last name + birthday + mobile number given at pre-registration
(a child without a mobile number can use the head of family's number).

- POST /resident/login   returns a resident token (12 hours), separate from staff tokens
- GET  /resident/me      own profile, current status, own history, family members and their logs,
                         active evacuation in the barangay, assigned GPS tracker
Residents never see other families, other barangays, or any staff dashboard data (RA 10173).
"""
import base64
import hashlib
import hmac
import os
import re
import time
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

import models
from database import get_db

router = APIRouter()
TOKEN_HOURS = 12
MAX_FAILS = 5
FAIL_WINDOW = 600
_fails = {}


class ResidentLogin(BaseModel):
    first_name: str = ''
    middle_name: str = ''
    last_name: str
    birthdate: str  # YYYY-MM-DD
    mobile_number: str


def _secret():
    return (os.environ.get("JWT_SECRET_KEY") or os.environ.get("SECRET_KEY") or "bilislikas-resident").encode()


def _make_token(evacuee_id):
    body = "%d.%d" % (evacuee_id, int(time.time()) + TOKEN_HOURS * 3600)
    sig = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode((body + "." + sig).encode()).decode()


def _read_token(token):
    try:
        eid, exp, sig = base64.urlsafe_b64decode(token.encode()).decode().split(".")
        good = hmac.new(_secret(), (eid + "." + exp).encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(sig, good) and int(exp) > time.time():
            return int(eid)
    except Exception:
        pass
    return None


def _digits(v):
    d = re.sub(r"\D", "", v or "")
    if d.startswith("63"):
        d = "0" + d[2:]
    if len(d) == 10 and d.startswith("9"):
        d = "0" + d
    return d


def _iso(dt):
    return dt.isoformat() + ("Z" if dt and dt.tzinfo is None else "") if dt else None


def _age(b):
    if not b:
        return None
    t = datetime.utcnow()
    return t.year - b.year - ((t.month, t.day) < (b.month, b.day))


@router.post("/resident/login")
def resident_login(p: ResidentLogin, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "?"
    now = time.time()
    recent = [t for t in _fails.get(ip, []) if now - t < FAIL_WINDOW]
    _fails[ip] = recent
    if len(recent) >= MAX_FAILS:
        raise HTTPException(status_code=429, detail="Too many attempts. Wait 10 minutes and try again.")
    last = " ".join(p.last_name.split()).lower()
    first = " ".join((p.first_name or '').split()).lower()
    middle = " ".join((p.middle_name or '').split()).lower()
    mobile = _digits(p.mobile_number)
    try:
        bday = datetime.strptime(p.birthdate.strip(), "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=422, detail="Choose your complete birthday.")
    if not first or not last or not re.fullmatch(r"09\d{9}", mobile):
        raise HTTPException(status_code=422, detail="Enter your first name, last name and a valid mobile number, such as 0917 123 4567.")
    E = models.Evacuee
    match = None
    for e in db.query(E).filter(E.birthdate.isnot(None)).all():
        if e.birthdate.date() != bday:
            continue
        words = (e.full_name or "").lower().split()
        if not words or " ".join(words[-len(last.split()):]) != last:
            continue
        if " ".join(words[:len(first.split())]) != first:
            continue
        if middle and middle not in " ".join(words):
            continue
        nums = {_digits(e.contact_number)}
        if e.household_id:
            h = db.get(models.Household, e.household_id)
            head = db.get(E, h.head_of_family_evacuee_id) if h and h.head_of_family_evacuee_id else None
            if head:
                nums.add(_digits(head.contact_number))
        if mobile in nums:
            match = e
            break
    if not match:
        _fails[ip].append(now)
        raise HTTPException(status_code=401, detail="No pre-registered resident matches these details. Check your name, birthday and mobile number, or ask your barangay office.")
    _fails.pop(ip, None)
    return {"token": _make_token(match.id), "full_name": match.full_name, "expires_in_hours": TOKEN_HOURS}


def _current_resident(authorization: str = Header(default=""), db: Session = Depends(get_db)):
    token = authorization.replace("Resident ", "").strip()
    eid = _read_token(token) if token else None
    e = db.get(models.Evacuee, eid) if eid else None
    if not e:
        raise HTTPException(status_code=401, detail="Please sign in again.")
    return e


def _status(e, db):
    last = (db.query(models.CheckinRecord).filter(models.CheckinRecord.evacuee_id == e.id)
            .order_by(models.CheckinRecord.id.desc()).first())
    if last and last.event_type == "check_in":
        c = db.get(models.EvacuationCenter, last.evacuation_center_id)
        return {"accounted": True, "center": c.name if c else None, "center_address": c.address if c else None, "since": _iso(last.timestamp)}
    return {"accounted": False, "center": None, "center_address": None, "since": _iso(last.timestamp) if last else None}


def _history(eid, db, limit=30):
    rows = (db.query(models.CheckinRecord).filter(models.CheckinRecord.evacuee_id == eid)
            .order_by(models.CheckinRecord.id.desc()).limit(limit).all())
    out = []
    for r in rows:
        c = db.get(models.EvacuationCenter, r.evacuation_center_id)
        out.append({"event": "Checked in" if r.event_type == "check_in" else "Checked out",
                    "center": c.name if c else None, "time": _iso(r.timestamp)})
    return out


@router.get("/resident/me")
def resident_me(e=Depends(_current_resident), db: Session = Depends(get_db)):
    E = models.Evacuee
    brgy = db.get(models.Barangay, e.registered_barangay_id) if e.registered_barangay_id else None
    tracker = db.query(models.Tracker).filter(models.Tracker.assigned_evacuee_id == e.id).first()
    tracker_info = None
    if tracker:
        ping = (db.query(models.GpsPing).filter(models.GpsPing.tracker_id == tracker.id)
                .order_by(models.GpsPing.id.desc()).first())
        tracker_info = {"device_id": tracker.device_id, "battery": tracker.battery_level,
                        "last_signal": _iso(ping.timestamp) if ping else None}
    family, head_name = [], None
    if e.household_id:
        h = db.get(models.Household, e.household_id)
        if h and h.head_of_family_evacuee_id:
            head = db.get(E, h.head_of_family_evacuee_id)
            head_name = head.full_name if head else None
        for m in db.query(E).filter(E.household_id == e.household_id, E.id != e.id).order_by(E.full_name).all():
            st = _status(m, db)
            family.append({"name": m.full_name, "age": _age(m.birthdate), "sex": m.sex,
                           "head": bool(m.is_head_of_family), "accounted": st["accounted"],
                           "center": st["center"], "since": st["since"], "history": _history(m.id, db, 10)})
    incident = None
    if e.registered_barangay_id:
        I = models.Incident
        i = (db.query(I).filter(I.barangay_id == e.registered_barangay_id, I.ended_at.is_(None))
             .order_by(I.id.desc()).first())
        if i:
            c = db.get(models.EvacuationCenter, i.evacuation_center_id) if i.evacuation_center_id else None
            incident = {"disaster_type": i.disaster_type, "started_at": _iso(i.started_at),
                        "center": c.name if c else None, "center_address": c.address if c else None}
    return {
        "profile": {
            "full_name": e.full_name, "birthdate": e.birthdate.date().isoformat() if e.birthdate else None,
            "age": _age(e.birthdate), "sex": e.sex, "civil_status": e.civil_status,
            "address": e.address, "contact_number": e.contact_number,
            "barangay": brgy.name if brgy else getattr(e, "home_barangay", None),
            "special_needs": [x for x in (e.special_needs or "").split(",") if x],
            "head_of_family": bool(e.is_head_of_family), "family_head": head_name,
            "face_registered": bool(e.facial_embedding),
        },
        "status": _status(e, db),
        "history": _history(e.id, db),
        "family": family,
        "evacuation": incident,
        "tracker": tracker_info,
    }
