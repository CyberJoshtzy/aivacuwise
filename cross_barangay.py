"""BilisLikas 2.0: cross-barangay evacuee tracking.

A resident is registered under a home barangay but may evacuate to a center of another barangay
(for example, a Barangay 200 resident who goes to Barrio Obrero Elementary School).

- GET /cross/status   for a barangay official (or City Admin with ?barangay_id=):
      away:   our residents who are checked in at another barangay's center (they are accounted for)
      guests: residents of other barangays who are checked in at our centers (basic details only)
- GET /cross/city     City Admin: per-center count of evacuees from other barangays

Privacy (RA 10173): guests are shown with name, sex, age, priority tags and home barangay only.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

import auth
import models
from database import get_db

router = APIRouter()


def _age(birthdate):
    try:
        b = (
            birthdate
            if isinstance(birthdate, datetime)
            else datetime.fromisoformat(str(birthdate)[:10])
        )
        t = datetime.utcnow()
        return t.year - b.year - ((t.month, t.day) < (b.month, b.day))
    except Exception:
        return None


def _priority(e):
    """Same rule as every page: senior 60+, child under 5, PWD, pregnant, medical need."""
    a = _age(e.birthdate)
    n = [x.strip() for x in (e.special_needs or "").split(",") if x.strip()]
    tags = []
    if (a is not None and a >= 60) or "Senior citizen" in n:
        tags.append("Senior")
    if a is not None and a < 5:
        tags.append("Child under 5")
    if "PWD" in n:
        tags.append("PWD")
    if "Pregnant" in n:
        tags.append("Pregnant")
    if any(x.startswith("Medical") for x in n):
        tags.append("Medical")
    return tags


def _iso(t):
    return t.isoformat() + "Z" if t else None


def _present(db: Session):
    """Every evacuee whose latest record is a check-in: (record, evacuee, center)."""
    latest = (
        db.query(
            models.CheckinRecord.evacuee_id.label("eid"),
            func.max(models.CheckinRecord.id).label("rid"),
        )
        .group_by(models.CheckinRecord.evacuee_id)
        .subquery()
    )
    return (
        db.query(models.CheckinRecord, models.Evacuee, models.EvacuationCenter)
        .join(latest, models.CheckinRecord.id == latest.c.rid)
        .join(models.Evacuee, models.Evacuee.id == models.CheckinRecord.evacuee_id)
        .join(
            models.EvacuationCenter,
            models.EvacuationCenter.id == models.CheckinRecord.evacuation_center_id,
        )
        .filter(models.CheckinRecord.event_type == "check_in")
        .all()
    )


def _names(db: Session):
    return {b.id: b.name for b in db.query(models.Barangay).all()}


@router.get("/cross/status")
def cross_status(
    barangay_id: int | None = None,
    db: Session = Depends(get_db),
    user=Depends(auth.get_current_user),
):
    if user.role == "city_admin":
        bid = barangay_id
        if bid is None:
            raise HTTPException(status_code=400, detail="Choose a barangay.")
    else:
        bid = user.barangay_id
        if bid is None:
            raise HTTPException(status_code=403, detail="Your account is not linked to a barangay.")
    names = _names(db)
    away, guests = [], []
    for rec, e, c in _present(db):
        home, host = e.registered_barangay_id, c.barangay_id
        if home is None or host is None or home == host:
            continue
        if home == bid:
            away.append(
                {
                    "evacuee_id": e.id,
                    "full_name": e.full_name,
                    "center_id": c.id,
                    "center_name": c.name,
                    "center_barangay": names.get(host, ""),
                    "checked_in_at": _iso(rec.timestamp),
                    "priority": _priority(e),
                }
            )
        elif host == bid:
            guests.append(
                {
                    "evacuee_id": e.id,
                    "full_name": e.full_name,
                    "sex": e.sex,
                    "age": _age(e.birthdate),
                    "priority": _priority(e),
                    "home_barangay": names.get(home, ""),
                    "center_id": c.id,
                    "center_name": c.name,
                    "checked_in_at": _iso(rec.timestamp),
                }
            )
    away.sort(key=lambda x: x["checked_in_at"] or "", reverse=True)
    guests.sort(key=lambda x: x["checked_in_at"] or "", reverse=True)
    return {"barangay_id": bid, "barangay_name": names.get(bid, ""), "away": away, "guests": guests}


@router.get("/cross/city")
def cross_city(db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    if user.role != "city_admin":
        raise HTTPException(status_code=403, detail="City Admin only.")
    names = _names(db)
    per = {}
    total = outside = 0
    for rec, e, c in _present(db):  # noqa: B007
        row = per.setdefault(
            c.id,
            {
                "center_id": c.id,
                "center_name": c.name,
                "barangay": names.get(c.barangay_id, ""),
                "total": 0,
                "outside": 0,
                "from": {},
            },
        )
        row["total"] += 1
        total += 1
        if e.registered_barangay_id and c.barangay_id and e.registered_barangay_id != c.barangay_id:
            row["outside"] += 1
            outside += 1
            h = names.get(e.registered_barangay_id, "")
            row["from"][h] = row["from"].get(h, 0) + 1
    centers = sorted(per.values(), key=lambda r: (-r["outside"], r["center_name"]))
    for r in centers:
        r["from"] = [
            {"barangay": k, "count": v} for k, v in sorted(r["from"].items(), key=lambda kv: -kv[1])
        ]
    return {
        "total_present": total,
        "outside_total": outside,
        "centers": [r for r in centers if r["outside"] > 0],
    }
