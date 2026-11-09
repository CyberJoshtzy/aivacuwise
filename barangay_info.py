"""Ai-Vacuwise: barangay profile (address, chairman, centers, residents).

- Adds barangays.address and barangays.zone (startup ALTER).
- GET /barangay_info               City Admin: every barangay. Official: own barangay only.
- PUT /barangays/{id}/info         update name, address and district
The chairman and mobile number come from the barangay's registered official accounts
(the designation chosen during barangay sign-up).
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, text
from sqlalchemy.orm import Session

import auth
import models
from database import engine, get_db

router = APIRouter()

try:
    with engine.begin() as conn:
        if conn.dialect.name == "postgresql":  # do not wait forever on a locked table
            conn.execute(text("SET LOCAL lock_timeout = '5s'"))
        conn.execute(text("ALTER TABLE barangays ADD COLUMN IF NOT EXISTS address VARCHAR"))
        conn.execute(text("ALTER TABLE barangays ADD COLUMN IF NOT EXISTS zone VARCHAR"))
except Exception as exc:
    print("barangay_info: could not add address column:", exc)

RANK = [
    "Barangay Chairman",
    "Barangay Captain",
    "Punong Barangay",
    "Barangay Kagawad",
    "SK Chairman",
    "Barangay Secretary",
]


class BarangayInfo(BaseModel):
    name: str
    address: str | None = None
    district: str | None = None
    zone: str | None = None


def clean_zone(z):
    z = " ".join((z or "").split())[:30]
    if z.isdigit():
        z = "Zone " + z
    return z or None


def _role(u):
    return u.role.value if hasattr(u.role, "value") else u.role


def _rank(u):
    d = (u.designation or "").strip()
    return RANK.index(d) if d in RANK else len(RANK)


def _addresses(db):
    try:
        return {
            r[0]: r[1] for r in db.execute(text("SELECT id, address FROM barangays")).fetchall()
        }
    except Exception:
        return {}


def _zones(db):
    try:
        return {r[0]: r[1] for r in db.execute(text("SELECT id, zone FROM barangays")).fetchall()}
    except Exception:
        return {}


@router.get("/barangay_info")
def barangay_info(user=Depends(auth.get_current_user), db: Session = Depends(get_db)):
    B, E, C, U = models.Barangay, models.Evacuee, models.EvacuationCenter, models.User
    q = db.query(B)
    if _role(user) != "city_admin":
        q = q.filter(B.id == user.barangay_id)
    addr = _addresses(db)
    zones = _zones(db)
    out = []
    for b in q.order_by(B.name).all():
        officials = [
            u
            for u in db.query(U).filter(U.barangay_id == b.id).all()
            if (getattr(u, "account_status", None) or "active") == "active"
        ]
        officials.sort(key=_rank)
        chair = officials[0] if officials else None
        out.append(
            {
                "id": b.id,
                "name": b.name,
                "district": getattr(b, "district", None),
                "address": addr.get(b.id),
                "zone": zones.get(b.id),
                "residents": db.query(func.count(E.id))
                .filter(E.registered_barangay_id == b.id)
                .scalar()
                or 0,
                "centers": [
                    c.name for c in db.query(C).filter(C.barangay_id == b.id).order_by(C.name).all()
                ],
                "chairman": {
                    "name": chair.full_name,
                    "designation": chair.designation,
                    "mobile": chair.mobile_number,
                    "email": chair.email,
                }
                if chair
                else None,
                "officials": [
                    {"name": u.full_name, "designation": u.designation, "mobile": u.mobile_number}
                    for u in officials
                ],
            }
        )
    return out


DISTRICTS = [
    "Binondo",
    "Ermita",
    "Intramuros",
    "Malate",
    "Paco",
    "Pandacan",
    "Port Area",
    "Quiapo",
    "Sampaloc",
    "San Andres",
    "San Miguel",
    "San Nicolas",
    "Santa Ana",
    "Santa Cruz",
    "Santa Mesa",
    "Tondo",
]


@router.put("/barangays/{barangay_id}/info")
def update_info(
    barangay_id: int,
    p: BarangayInfo,
    user=Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    B = models.Barangay
    city = _role(user) == "city_admin"
    if not city and user.barangay_id != barangay_id:
        raise HTTPException(status_code=403, detail="You can only edit your own barangay.")
    b = db.get(B, barangay_id)
    if not b:
        raise HTTPException(status_code=404, detail="Barangay not found.")
    name = " ".join((p.name or "").split())
    if not name:
        raise HTTPException(status_code=422, detail="Barangay name cannot be empty.")
    if db.query(B).filter(func.lower(B.name) == name.lower(), B.id != barangay_id).first():
        raise HTTPException(status_code=409, detail="Another barangay already uses this name.")
    b.name = name
    if hasattr(b, "district") and p.district is not None:
        d = (p.district or "").strip() or None
        if d and d not in DISTRICTS:
            raise HTTPException(status_code=422, detail="Choose one of the 16 districts of Manila.")
        b.district = d
    db.commit()
    db.execute(
        text("UPDATE barangays SET address = :a WHERE id = :i"),
        {"a": " ".join((p.address or "").split()) or None, "i": barangay_id},
    )
    if p.zone is not None:
        db.execute(
            text("UPDATE barangays SET zone = :z WHERE id = :i"),
            {"z": clean_zone(p.zone), "i": barangay_id},
        )
    db.commit()
    return {"id": b.id, "name": b.name}
