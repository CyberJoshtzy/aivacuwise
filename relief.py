"""BilisLikas 2.0: relief goods and medicine distribution log.

Barangay officials record what was given (food, water, medicine, hygiene, other);
the City Admin sees every barangay's totals on City Overview (synced through the cloud hub).

- GET    /relief/items              suggested items per category
- GET    /relief                    records (City Admin: all, official: own barangay); ?barangay_id=
- POST   /relief                    add a record
- DELETE /relief/{id}               remove a record (own barangay, or City Admin)
- GET    /relief/summary            per-barangay totals by category and item
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

import auth
import models
from database import get_db

router = APIRouter()

try:  # create the table on this server (local laptop or cloud hub) if it is new
    from database import engine as _engine

    models.ReliefRecord.__table__.create(_engine, checkfirst=True)
except Exception as exc:
    print("relief: could not create relief_records table:", exc)

CATEGORIES = ["Food", "Water", "Medicine", "Hygiene", "Other"]
ITEMS = {
    "Food": [
        "Sopas",
        "Champorado",
        "Lugaw",
        "Arroz caldo",
        "Rice",
        "Canned goods",
        "Instant noodles",
        "Bread",
        "Biscuits",
        "Hot meal (packed)",
    ],
    "Water": ["Bottled water", "Water gallon", "Water refill"],
    "Medicine": [
        "Biogesic (Paracetamol)",
        "Neozep",
        "Bioflu",
        "Decolgen",
        "Diatabs (Loperamide)",
        "ORS (Oral rehydration salts)",
        "Amoxicillin",
        "Cetirizine",
        "Betadine",
        "Rubbing alcohol",
        "Doxycycline (leptospirosis prevention)",
    ],
    "Hygiene": [
        "Hygiene kit",
        "Soap",
        "Toothpaste and toothbrush",
        "Diapers",
        "Sanitary napkins",
        "Face masks",
    ],
    "Other": ["Blanket", "Sleeping mat", "Clothes", "Flashlight", "Milk for infants"],
}
UNITS = [
    "pcs",
    "packs",
    "servings",
    "bowls",
    "bottles",
    "gallons",
    "tablets",
    "capsules",
    "sachets",
    "kg",
    "boxes",
    "kits",
    "sets",
]


class ReliefIn(BaseModel):
    barangay_id: int | None = None
    evacuation_center_id: int | None = None
    category: str
    item: str
    quantity: float
    unit: str
    recipients: int | None = None
    given_at: str | None = None
    notes: str | None = None


def _role(u):
    return u.role.value if hasattr(u.role, "value") else u.role


def _iso(dt):
    return dt.isoformat() + "Z" if dt else None


def _dict(r, db, cache):
    def name(model, i):
        if not i:
            return None
        k = (model.__tablename__, i)
        if k not in cache:
            o = db.get(model, i)
            cache[k] = o.name if o else None
        return cache[k]

    by = db.get(models.User, r.recorded_by) if r.recorded_by else None
    return {
        "id": r.id,
        "barangay_id": r.barangay_id,
        "barangay": name(models.Barangay, r.barangay_id),
        "evacuation_center_id": r.evacuation_center_id,
        "center": name(models.EvacuationCenter, r.evacuation_center_id),
        "category": r.category,
        "item": r.item,
        "quantity": r.quantity,
        "unit": r.unit,
        "recipients": r.recipients,
        "given_at": _iso(r.given_at),
        "notes": r.notes,
        "recorded_by": by.full_name if by else None,
    }


@router.get("/relief/items")
def relief_items():
    return {"categories": CATEGORIES, "items": ITEMS, "units": UNITS}


@router.get("/relief")
def relief_list(
    barangay_id: int | None = None,
    user=Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    R = models.ReliefRecord
    q = db.query(R)
    if _role(user) != "city_admin":
        q = q.filter(R.barangay_id == user.barangay_id)
    elif barangay_id:
        q = q.filter(R.barangay_id == barangay_id)
    cache = {}
    return [
        _dict(r, db, cache) for r in q.order_by(R.given_at.desc(), R.id.desc()).limit(500).all()
    ]


@router.post("/relief", status_code=201)
def relief_add(p: ReliefIn, user=Depends(auth.get_current_user), db: Session = Depends(get_db)):
    city = _role(user) == "city_admin"
    bid = p.barangay_id if city else user.barangay_id
    if not bid or not db.get(models.Barangay, bid):
        raise HTTPException(status_code=422, detail="Choose the barangay.")
    if p.category not in CATEGORIES:
        raise HTTPException(status_code=422, detail="Choose a category.")
    item = " ".join((p.item or "").split())
    if not item:
        raise HTTPException(status_code=422, detail="Enter the item given.")
    if not p.quantity or p.quantity <= 0:
        raise HTTPException(status_code=422, detail="Enter a quantity greater than zero.")
    unit = " ".join((p.unit or "").split()) or "pcs"
    if p.evacuation_center_id:
        c = db.get(models.EvacuationCenter, p.evacuation_center_id)
        if not c or c.barangay_id != bid:
            raise HTTPException(
                status_code=422, detail="That evacuation center is not in this barangay."
            )
    when = datetime.utcnow()
    if p.given_at:
        try:
            when = datetime.fromisoformat(p.given_at.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid date and time.")  # noqa: B904
    r = models.ReliefRecord(
        barangay_id=bid,
        evacuation_center_id=p.evacuation_center_id or None,
        category=p.category,
        item=item,
        quantity=p.quantity,
        unit=unit,
        recipients=p.recipients or None,
        given_at=when,
        notes=(p.notes or "").strip() or None,
        recorded_by=user.id,
    )
    db.add(r)
    db.commit()
    return _dict(r, db, {})


@router.delete("/relief/{rid}")
def relief_delete(rid: int, user=Depends(auth.get_current_user), db: Session = Depends(get_db)):
    r = db.get(models.ReliefRecord, rid)
    if not r:
        raise HTTPException(status_code=404, detail="Record not found.")
    if _role(user) != "city_admin" and r.barangay_id != user.barangay_id:
        raise HTTPException(
            status_code=403, detail="You can only remove your own barangay's records."
        )
    db.delete(r)
    db.commit()
    return {"ok": True}


@router.get("/relief/summary")
def relief_summary(user=Depends(auth.get_current_user), db: Session = Depends(get_db)):
    R = models.ReliefRecord
    q = db.query(R)
    if _role(user) != "city_admin":
        q = q.filter(R.barangay_id == user.barangay_id)
    out = {}
    for r in q.all():
        b = out.setdefault(
            r.barangay_id,
            {
                "barangay_id": r.barangay_id,
                "records": 0,
                "recipients": 0,
                "last_given": None,
                "categories": {c: 0 for c in CATEGORIES},
                "items": {},
            },
        )
        b["records"] += 1
        b["recipients"] += r.recipients or 0
        b["categories"][r.category] = b["categories"].get(r.category, 0) + 1
        key = r.item + "|" + r.unit
        it = b["items"].setdefault(
            key, {"item": r.item, "unit": r.unit, "category": r.category, "quantity": 0}
        )
        it["quantity"] += r.quantity or 0
        if r.given_at and (b["last_given"] is None or r.given_at > b["last_given"]):
            b["last_given"] = r.given_at
    res = []
    for b in out.values():
        b["last_given"] = _iso(b["last_given"])
        b["items"] = sorted(
            b["items"].values(),
            key=lambda x: (
                CATEGORIES.index(x["category"]) if x["category"] in CATEGORIES else 9,
                -x["quantity"],
            ),
        )
        res.append(b)
    return res
