"""BilisLikas 2.0: City Hall administrator accounts.

- Adds position, office, employee_id, account_status and is_superuser to users (startup ALTER).
- Existing city_admin accounts made before this change become System Administrators (superusers).
- GET  /admin/register/config        dropdown choices for the sign-up page
- POST /admin/register               City Hall sign-up, needs ADMIN_REGISTRATION_CODE, starts as pending
- GET  /admin/me                     position, office and superuser flag of the signed-in admin
- GET  /admin/users                  all accounts (superuser only)
- POST /admin/users/{id}/approve | reject | disable | enable   (superuser only)
"""

import os
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, text
from sqlalchemy.orm import Session

import auth
import models
from database import get_db

router = APIRouter()

POSITIONS = [
    {"value": "mayor", "label": "City Mayor", "office": "mayor"},
    {"value": "vice_mayor", "label": "City Vice Mayor", "office": "mayor"},
    {
        "value": "cdrrmo_head",
        "label": "City Disaster Risk Reduction and Management Officer (CDRRMO Head)",
        "office": "cdrrmo",
    },
    {
        "value": "cdrrmo_staff",
        "label": "City Disaster Risk Reduction and Management Office Staff (CDRRMO Staff)",
        "office": "cdrrmo",
    },
    {
        "value": "cswdo_staff",
        "label": "City Social Welfare and Development Office Staff (CSWDO Staff)",
        "office": "cswdo",
    },
    {"value": "cho_staff", "label": "City Health Office Staff (CHO Staff)", "office": "cho"},
    {
        "value": "mis_admin",
        "label": "Management Information Systems Administrator (MIS Administrator)",
        "office": "mis",
    },
]
OFFICES = [
    {"value": "mayor", "label": "Office of the City Mayor"},
    {"value": "cdrrmo", "label": "City Disaster Risk Reduction and Management Office (CDRRMO)"},
    {"value": "cswdo", "label": "City Social Welfare and Development Office (CSWDO)"},
    {"value": "cho", "label": "City Health Office (CHO)"},
    {"value": "mis", "label": "Management Information Systems Office (MIS)"},
]
POS_LABEL = {p["value"]: p["label"] for p in POSITIONS}
OFF_LABEL = {o["value"]: o["label"] for o in OFFICES}

try:  # add the new columns if this database was created before them
    from database import engine as _engine

    if _engine.dialect.name == "postgresql":
        with _engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS position VARCHAR"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS office VARCHAR"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS employee_id VARCHAR"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS account_status VARCHAR"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_superuser BOOLEAN"))
            conn.execute(
                text(
                    "UPDATE users SET is_superuser = TRUE WHERE role = 'city_admin' AND position IS NULL AND is_superuser IS NULL"
                )
            )
except Exception as exc:  # the app still starts; the error is shown in the server log
    print("admin_auth: could not add new columns:", exc)


class AdminRegister(BaseModel):
    first_name: str
    middle_name: str | None = None
    last_name: str
    email: str
    position: str
    office: str
    employee_id: str
    mobile_number: str
    password: str
    registration_code: str | None = None


def _is_super(user):
    return getattr(user, "role", None) in ("city_admin", models.UserRole.city_admin) and bool(
        getattr(user, "is_superuser", False)
    )


def _require_super(user=Depends(auth.get_current_user)):
    if not _is_super(user):
        raise HTTPException(
            status_code=403, detail="Only the City Hall IT Administrator can do this."
        )
    return user


def _role(u):
    return u.role.value if hasattr(u.role, "value") else u.role


def _user_dict(u, db):
    brgy = db.get(models.Barangay, u.barangay_id) if u.barangay_id else None
    return {
        "id": u.id,
        "full_name": u.full_name,
        "email": u.email,
        "mobile_number": u.mobile_number,
        "role": _role(u),
        "is_superuser": bool(u.is_superuser),
        "position": POS_LABEL.get(u.position or "", u.designation or u.position),
        "office": OFF_LABEL.get(u.office or "", u.office),
        "employee_id": u.employee_id,
        "barangay": brgy.name if brgy else None,
        "status": u.account_status or "active",
        "is_it_admin": _is_it(u),
    }


def _is_it(u):
    import approvals

    return approvals.is_it_admin(u)


def _require_it(user=Depends(auth.get_current_user)):
    if not _is_it(user):
        raise HTTPException(
            status_code=403, detail="Only the City Hall IT Administrator can approve or reject."
        )
    return user


@router.get("/admin/register/config")
def admin_register_config():
    return {
        "positions": POSITIONS,
        "offices": OFFICES,
        "code_required": bool((os.environ.get("ADMIN_REGISTRATION_CODE") or "").strip()),
    }


@router.post("/admin/register", status_code=201)
def admin_register(p: AdminRegister, db: Session = Depends(get_db)):
    first, last = " ".join(p.first_name.split()), " ".join(p.last_name.split())
    middle = " ".join((p.middle_name or "").split())
    if not first or not last:
        raise HTTPException(status_code=422, detail="Enter your first and last name.")
    email = p.email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    if p.position not in POS_LABEL:
        raise HTTPException(status_code=422, detail="Choose your position.")
    if p.office not in OFF_LABEL:
        raise HTTPException(status_code=422, detail="Choose your office or department.")
    emp = p.employee_id.strip()
    if not emp:
        raise HTTPException(status_code=422, detail="Enter your employee ID number.")
    digits = re.sub(r"\D", "", p.mobile_number or "")
    if digits.startswith("63"):
        digits = "0" + digits[2:]
    if len(digits) == 10 and digits.startswith("9"):
        digits = "0" + digits
    if not re.fullmatch(r"09\d{9}", digits):
        raise HTTPException(
            status_code=422, detail="Enter a valid Philippine mobile number, such as 0917 123 4567."
        )
    pw = p.password or ""
    if len(pw) < 8 or not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        raise HTTPException(
            status_code=422,
            detail="Use a password with at least 8 characters, including letters and a number.",
        )
    U = models.User
    if db.query(U).filter(or_email(U, email)).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    full = " ".join(x for x in (first, middle, last) if x)
    u = U(
        username=email,
        email=email,
        password_hash=auth.get_password_hash(pw),
        role="city_admin",
        full_name=full,
        designation=POS_LABEL[p.position],
        mobile_number=digits,
        position=p.position,
        office=p.office,
        employee_id=emp,
        account_status="pending",
        is_superuser=False,
    )
    db.add(u)
    db.commit()
    return {"id": u.id, "email": email, "status": "pending"}


def or_email(U, email):
    return (func.lower(U.email) == email) | (func.lower(U.username) == email)


@router.get("/admin/me")
def admin_me(user=Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return _user_dict(user, db)


@router.get("/admin/users")
def admin_users(user=Depends(_require_super), db: Session = Depends(get_db)):
    order = {"pending": 0, "active": 1, "disabled": 2, "rejected": 3}
    rows = [_user_dict(u, db) for u in db.query(models.User).all()]
    rows.sort(
        key=lambda r: (
            order.get(r["status"], 9),
            r["role"] != "city_admin",
            (r["full_name"] or "").lower(),
        )
    )
    return rows


def _set_status(user_id, status, me, db):
    u = db.get(models.User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="Account not found.")
    if u.id == me.id:
        raise HTTPException(status_code=409, detail="You cannot change your own account.")
    u.account_status = status
    db.commit()
    return _user_dict(u, db)


@router.post("/admin/users/{user_id}/approve")
def approve(user_id: int, me=Depends(_require_it), db: Session = Depends(get_db)):
    return _set_status(user_id, "active", me, db)


@router.post("/admin/users/{user_id}/reject")
def reject(user_id: int, me=Depends(_require_it), db: Session = Depends(get_db)):
    u = db.get(models.User, user_id)
    if u and (u.account_status or "active") == "pending" and _role(u) == "barangay_official":
        import approvals

        approvals.undo_signup(
            db, u
        )  # remove the barangay and centers that only this sign-up created
    return _set_status(user_id, "rejected", me, db)


@router.post("/admin/users/{user_id}/disable")
def disable(user_id: int, me=Depends(_require_super), db: Session = Depends(get_db)):
    return _set_status(user_id, "disabled", me, db)


@router.post("/admin/users/{user_id}/enable")
def enable(user_id: int, me=Depends(_require_super), db: Session = Depends(get_db)):
    return _set_status(user_id, "active", me, db)
