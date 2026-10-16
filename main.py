import json
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import auth
import models
import schemas
from connection_manager import manager
from database import get_db

app = FastAPI()


@app.get("/")
def read_root():
    return {"status": "BilisLikas 2.0 backend is running"}


@app.post("/barangays", response_model=schemas.BarangayOut)
def create_barangay(barangay: schemas.BarangayCreate, db: Session = Depends(get_db)):
    db_barangay = models.Barangay(name=barangay.name)
    db.add(db_barangay)
    db.commit()
    db.refresh(db_barangay)
    return db_barangay


@app.get("/barangays", response_model=list[schemas.BarangayOut])
def list_barangays(db: Session = Depends(get_db)):
    return db.query(models.Barangay).all()


@app.post("/evacuation_centers", response_model=schemas.EvacuationCenterOut)
def create_center(
    center: schemas.EvacuationCenterCreate,
    db: Session = Depends(get_db),
    current_user=Depends(auth.get_current_user),
):
    import approvals

    if not approvals.is_it_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail="Only the City Hall IT Administrator can add evacuation centers.",
        )
    db_center = models.EvacuationCenter(**center.model_dump())
    db.add(db_center)
    db.commit()
    db.refresh(db_center)
    return db_center


@app.get("/evacuation_centers", response_model=list[schemas.EvacuationCenterOut])
def list_centers(db: Session = Depends(get_db)):
    return db.query(models.EvacuationCenter).all()


@app.post("/evacuees", response_model=schemas.EvacueeOut)
def register_evacuee(evacuee: schemas.EvacueeCreate, db: Session = Depends(get_db)):
    db_evacuee = models.Evacuee(**evacuee.model_dump())
    db.add(db_evacuee)
    db.commit()
    db.refresh(db_evacuee)
    return db_evacuee


@app.get("/evacuees", response_model=list[schemas.EvacueeOut])
def list_evacuees(db: Session = Depends(get_db)):
    return db.query(models.Evacuee).all()


@app.post("/checkin", response_model=schemas.CheckinOut)
async def checkin_evacuee(record: schemas.CheckinCreate, db: Session = Depends(get_db)):
    evacuee = db.query(models.Evacuee).filter(models.Evacuee.id == record.evacuee_id).first()
    if not evacuee:
        raise HTTPException(status_code=404, detail="Evacuee not found")
    center = (
        db.query(models.EvacuationCenter)
        .filter(models.EvacuationCenter.id == record.evacuation_center_id)
        .first()
    )
    if not center:
        raise HTTPException(status_code=404, detail="Evacuation center not found")
    db_record = models.CheckinRecord(**record.model_dump())
    db.add(db_record)
    if record.event_type == "check_in":
        # Infants (no face data) are checked in together with their parent or guardian.
        for infant in (
            db.query(models.Evacuee).filter(models.Evacuee.guardian_evacuee_id == evacuee.id).all()
        ):
            last = (
                db.query(models.CheckinRecord)
                .filter(models.CheckinRecord.evacuee_id == infant.id)
                .order_by(models.CheckinRecord.id.desc())
                .first()
            )
            if (
                last is None
                or last.event_type != "check_in"
                or last.evacuation_center_id != center.id
            ):
                db.add(
                    models.CheckinRecord(
                        evacuee_id=infant.id,
                        evacuation_center_id=center.id,
                        event_type="check_in",
                        timestamp=datetime.utcnow(),
                    )
                )
    db.commit()
    db.refresh(db_record)
    await manager.broadcast({"type": "occupancy_update", "barangay_id": center.barangay_id})
    return db_record


def _get_current_evacuees_at_center(db: Session, center_id: int):
    latest_sub = (
        db.query(
            models.CheckinRecord.evacuee_id.label("evacuee_id"),
            func.max(models.CheckinRecord.id).label("latest_id"),
        )
        .group_by(models.CheckinRecord.evacuee_id)
        .subquery()
    )

    latest_records = (
        db.query(models.CheckinRecord)
        .join(latest_sub, models.CheckinRecord.id == latest_sub.c.latest_id)
        .filter(models.CheckinRecord.evacuation_center_id == center_id)
        .filter(models.CheckinRecord.event_type == "check_in")
        .all()
    )

    evacuee_ids = [r.evacuee_id for r in latest_records]
    return db.query(models.Evacuee).filter(models.Evacuee.id.in_(evacuee_ids)).all()


@app.get("/evacuation_centers/{center_id}/evacuees")
def evacuees_at_center(center_id: int, db: Session = Depends(get_db)):
    return _get_current_evacuees_at_center(db, center_id)


@app.post("/users", response_model=schemas.UserOut)
def bootstrap_first_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    existing_count = db.query(models.User).count()
    if existing_count > 0:
        raise HTTPException(
            status_code=403,
            detail="User creation is closed. Ask a city admin to create your account via /admin/users.",
        )
    hashed_password = auth.get_password_hash(user.password)
    db_user = models.User(
        email=(user.email.strip().lower() if getattr(user, "email", None) else None),
        username=user.username,
        password_hash=hashed_password,
        role=user.role,
        barangay_id=user.barangay_id,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


@app.post("/admin/users", response_model=schemas.UserOut)
def admin_create_user(
    user: schemas.UserCreate,
    current_user: models.User = Depends(auth.require_role("city_admin")),
    db: Session = Depends(get_db),
):
    hashed_password = auth.get_password_hash(user.password)
    db_user = models.User(
        email=(user.email.strip().lower() if getattr(user, "email", None) else None),
        username=user.username,
        password_hash=hashed_password,
        role=user.role,
        barangay_id=user.barangay_id,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


from fastapi import Request as _LLRequest

import login_log


@app.post("/login", response_model=schemas.Token)
def login(
    request: _LLRequest,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = (
        db.query(models.User)
        .filter(
            or_(
                models.User.username == form_data.username,
                models.User.email == form_data.username.strip().lower(),
            )
        )
        .first()
    )
    if not user or not auth.verify_password(form_data.password, user.password_hash):
        login_log.record(db, request, user, form_data.username, "failed", "Wrong email or password")
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    status = getattr(user, "account_status", None) or "active"
    if status == "pending":
        login_log.record(db, request, user, form_data.username, "blocked", "Waiting for approval")
        raise HTTPException(
            status_code=403,
            detail="Your account is waiting for approval by the City Hall IT Administrator.",
        )
    if status in ("rejected", "disabled"):
        login_log.record(db, request, user, form_data.username, "blocked", "Account " + status)
        raise HTTPException(
            status_code=403,
            detail="This account is not active. Contact the City Hall IT Administrator.",
        )
    login_log.record(db, request, user, form_data.username, "success")
    access_token = auth.create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/users/me", response_model=schemas.UserOut)
def read_current_user(current_user: models.User = Depends(auth.get_current_user)):
    return current_user


@app.post("/trackers", response_model=schemas.TrackerOut)
def create_tracker(tracker: schemas.TrackerCreate, db: Session = Depends(get_db)):
    new_tracker = models.Tracker(**tracker.model_dump())
    db.add(new_tracker)
    db.commit()
    db.refresh(new_tracker)
    return new_tracker


@app.get("/trackers", response_model=list[schemas.TrackerOut])
def list_trackers(db: Session = Depends(get_db)):
    return db.query(models.Tracker).all()


@app.post("/gps_pings", response_model=schemas.GpsPingOut)
async def create_gps_ping(ping: schemas.GpsPingCreate, db: Session = Depends(get_db)):
    tracker = db.query(models.Tracker).filter(models.Tracker.id == ping.tracker_id).first()
    if not tracker:
        raise HTTPException(status_code=404, detail="Tracker not found")
    new_ping = models.GpsPing(**ping.model_dump())
    db.add(new_ping)
    db.commit()
    db.refresh(new_ping)
    await manager.broadcast({"type": "gps_update", "barangay_id": None, "tracker_id": tracker.id})
    return new_ping


@app.get("/gps_pings/{tracker_id}/latest", response_model=schemas.GpsPingOut)
def get_latest_ping(tracker_id: int, db: Session = Depends(get_db)):
    ping = (
        db.query(models.GpsPing)
        .filter(models.GpsPing.tracker_id == tracker_id)
        .order_by(models.GpsPing.timestamp.desc())
        .first()
    )
    if not ping:
        raise HTTPException(status_code=404, detail="No location data found for this tracker")
    return ping


@app.get("/gps_pings/{tracker_id}/history", response_model=list[schemas.GpsPingOut])
def get_ping_history(tracker_id: int, db: Session = Depends(get_db)):
    return (
        db.query(models.GpsPing)
        .filter(models.GpsPing.tracker_id == tracker_id)
        .order_by(models.GpsPing.timestamp.desc())
        .limit(20)
        .all()
    )


@app.post("/checkin/walkin", response_model=schemas.WalkinCheckinOut)
async def walkin_register_and_checkin(
    data: schemas.WalkinCheckinCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    center = (
        db.query(models.EvacuationCenter)
        .filter(models.EvacuationCenter.id == data.evacuation_center_id)
        .first()
    )
    if not center:
        raise HTTPException(status_code=404, detail="Evacuation center not found")

    new_evacuee = models.Evacuee(
        full_name=data.full_name,
        birthdate=data.birthdate,
        sex=data.sex,
        address=data.address,
        contact_number=data.contact_number,
        registered_barangay_id=data.registered_barangay_id,
        facial_embedding=None,
        identification_method="manual",
    )
    db.add(new_evacuee)
    db.flush()

    new_checkin = models.CheckinRecord(
        evacuee_id=new_evacuee.id,
        evacuation_center_id=data.evacuation_center_id,
        event_type="check_in",
        timestamp=datetime.utcnow(),
    )
    db.add(new_checkin)

    db.commit()
    db.refresh(new_evacuee)
    db.refresh(new_checkin)

    await manager.broadcast({"type": "occupancy_update", "barangay_id": center.barangay_id})

    return {"evacuee": new_evacuee, "checkin": new_checkin}


@app.get("/evacuees/{evacuee_id}/history", response_model=list[schemas.CheckinOut])
def evacuee_movement_history(evacuee_id: int, db: Session = Depends(get_db)):
    evacuee = db.query(models.Evacuee).filter(models.Evacuee.id == evacuee_id).first()
    if not evacuee:
        raise HTTPException(status_code=404, detail="Evacuee not found")
    return (
        db.query(models.CheckinRecord)
        .filter(models.CheckinRecord.evacuee_id == evacuee_id)
        .order_by(models.CheckinRecord.id.desc())
        .all()
    )


@app.get("/dashboard/summary")
def dashboard_summary(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    barangays_query = db.query(models.Barangay)
    if current_user.role != "city_admin":
        barangays_query = barangays_query.filter(models.Barangay.id == current_user.barangay_id)
    barangays = barangays_query.all()

    barangay_list = []
    for barangay in barangays:
        centers = (
            db.query(models.EvacuationCenter)
            .filter(models.EvacuationCenter.barangay_id == barangay.id)
            .all()
        )
        center_list = []
        for center in centers:
            evacuees = _get_current_evacuees_at_center(db, center.id)
            center_list.append(
                {
                    "id": center.id,
                    "name": center.name,
                    "capacity": center.capacity,
                    "occupancy": len(evacuees),
                    "evacuees": [
                        {
                            "id": e.id,
                            "full_name": e.full_name,
                            "identification_method": e.identification_method,
                        }
                        for e in evacuees
                    ],
                }
            )
        barangay_list.append(
            {
                "id": barangay.id,
                "name": barangay.name,
                "centers": center_list,
            }
        )

    trackers = db.query(models.Tracker).filter(models.Tracker.assigned_evacuee_id.isnot(None)).all()
    tracker_list = []
    for t in trackers:
        latest_ping = (
            db.query(models.GpsPing)
            .filter(models.GpsPing.tracker_id == t.id)
            .order_by(models.GpsPing.timestamp.desc())
            .first()
        )
        if latest_ping:
            evacuee = (
                db.query(models.Evacuee).filter(models.Evacuee.id == t.assigned_evacuee_id).first()
            )
            tracker_list.append(
                {
                    "tracker_id": t.id,
                    "device_id": t.device_id,
                    "evacuee_id": t.assigned_evacuee_id,
                    "evacuee_name": evacuee.full_name if evacuee else None,
                    "latitude": latest_ping.latitude,
                    "longitude": latest_ping.longitude,
                    "timestamp": latest_ping.timestamp.isoformat(),
                }
            )

    return {"barangays": barangay_list, "trackers": tracker_list}


@app.websocket("/ws/dashboard")
async def dashboard_websocket(websocket: WebSocket, token: str, db: Session = Depends(get_db)):
    user = auth.get_current_user_from_token(token, db)
    if user is None:
        await websocket.close(code=1008)
        return
    await manager.connect(websocket, user)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.get("/dashboard")
def dashboard_page():
    return FileResponse("static/dashboard.html")


@app.post("/households", response_model=schemas.HouseholdOut)
async def create_household(
    household: schemas.HouseholdCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    barangay = (
        db.query(models.Barangay)
        .filter(models.Barangay.id == household.registered_barangay_id)
        .first()
    )
    if not barangay:
        raise HTTPException(status_code=404, detail="Barangay not found")
    if not household.members:
        raise HTTPException(status_code=400, detail="A household needs at least one member")

    head_count = sum(1 for m in household.members if m.is_head_of_family)
    if head_count > 1:
        raise HTTPException(
            status_code=400, detail="Only one member can be marked as head of family"
        )

    db_household = models.Household(registered_barangay_id=household.registered_barangay_id)
    db.add(db_household)
    db.flush()

    member_records = []
    head_evacuee_id = None
    for member in household.members:
        evacuee = models.Evacuee(
            full_name=member.full_name,
            birthdate=member.birthdate,
            sex=member.sex,
            address=member.address,
            contact_number=member.contact_number,
            registered_barangay_id=household.registered_barangay_id,
            household_id=db_household.id,
            is_head_of_family=member.is_head_of_family,
            identification_method="facial_recognition",
        )
        db.add(evacuee)
        db.flush()
        member_records.append(evacuee)
        if member.is_head_of_family:
            head_evacuee_id = evacuee.id

    if head_evacuee_id is not None:
        db_household.head_of_family_evacuee_id = head_evacuee_id

    db.commit()
    db.refresh(db_household)

    return {
        "id": db_household.id,
        "registered_barangay_id": db_household.registered_barangay_id,
        "head_of_family_evacuee_id": db_household.head_of_family_evacuee_id,
        "created_at": db_household.created_at,
        "members": member_records,
    }


@app.get("/households/{household_id}", response_model=schemas.HouseholdOut)
def get_household(household_id: int, db: Session = Depends(get_db)):
    household = db.query(models.Household).filter(models.Household.id == household_id).first()
    if not household:
        raise HTTPException(status_code=404, detail="Household not found")
    members = db.query(models.Evacuee).filter(models.Evacuee.household_id == household_id).all()
    return {
        "id": household.id,
        "registered_barangay_id": household.registered_barangay_id,
        "head_of_family_evacuee_id": household.head_of_family_evacuee_id,
        "created_at": household.created_at,
        "members": members,
    }


@app.get("/barangays/{barangay_id}/households", response_model=list[schemas.HouseholdOut])
def list_households_for_barangay(barangay_id: int, db: Session = Depends(get_db)):
    households = (
        db.query(models.Household)
        .filter(models.Household.registered_barangay_id == barangay_id)
        .all()
    )
    result = []
    for h in households:
        members = db.query(models.Evacuee).filter(models.Evacuee.household_id == h.id).all()
        result.append(
            {
                "id": h.id,
                "registered_barangay_id": h.registered_barangay_id,
                "head_of_family_evacuee_id": h.head_of_family_evacuee_id,
                "created_at": h.created_at,
                "members": members,
            }
        )
    return result


@app.get("/households/{household_id}/status", response_model=schemas.HouseholdStatusOut)
def household_status(household_id: int, db: Session = Depends(get_db)):
    household = db.query(models.Household).filter(models.Household.id == household_id).first()
    if not household:
        raise HTTPException(status_code=404, detail="Household not found")
    members = db.query(models.Evacuee).filter(models.Evacuee.household_id == household_id).all()
    statuses = []
    for m in members:
        latest_event = (
            db.query(models.CheckinRecord)
            .filter(models.CheckinRecord.evacuee_id == m.id)
            .order_by(models.CheckinRecord.id.desc())
            .first()
        )
        current_center_id = None
        current_center_name = None
        if latest_event and latest_event.event_type == "check_in":
            center = (
                db.query(models.EvacuationCenter)
                .filter(models.EvacuationCenter.id == latest_event.evacuation_center_id)
                .first()
            )
            if center:
                current_center_id = center.id
                current_center_name = center.name
        statuses.append(
            {
                "evacuee_id": m.id,
                "full_name": m.full_name,
                "is_head_of_family": m.is_head_of_family or False,
                "current_center_id": current_center_id,
                "current_center_name": current_center_name,
            }
        )
    return {"household_id": household_id, "members": statuses}


@app.get("/kiosk")
async def kiosk():
    return FileResponse("static/kiosk.html")


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.post("/evacuees/{evacuee_id}/facial_embedding")
def set_facial_embedding(
    evacuee_id: int,
    payload: schemas.FacialEmbeddingIn,
    db: Session = Depends(get_db),
    current_user=Depends(auth.get_current_user),
):
    evacuee = db.query(models.Evacuee).filter(models.Evacuee.id == evacuee_id).first()
    if not evacuee:
        raise HTTPException(status_code=404, detail="Evacuee not found")
    evacuee.facial_embedding = json.dumps(payload.embedding)
    evacuee.identification_method = "facial_recognition"
    db.commit()
    return {"evacuee_id": evacuee_id, "status": "embedding saved"}


@app.get("/evacuees/enrolled_faces", response_model=list[schemas.EnrolledFaceOut])
def enrolled_faces(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    evacuees = db.query(models.Evacuee).filter(models.Evacuee.facial_embedding.isnot(None)).all()
    result = []
    for e in evacuees:
        try:
            embedding = json.loads(e.facial_embedding)
        except TypeError, ValueError:
            continue
        result.append({"evacuee_id": e.id, "full_name": e.full_name, "embedding": embedding})
    return result


# ---- BilisLikas 2.0: edit and delete endpoints (batch 2) ----
from datetime import date as _BLDate

from fastapi import Depends as _BLDepends
from fastapi import HTTPException as _BLHTTPException
from pydantic import BaseModel as _BLBaseModel
from sqlalchemy import String as _BLString
from sqlalchemy.orm import Session as _BLSession


def _bl_model(table):
    key = "_" * 2 + "tablename" + "_" * 2
    for obj in vars(models).values():
        if isinstance(obj, type) and getattr(obj, key, None) == table:
            return obj
    raise RuntimeError("No model found for table " + table)


class BLEvacueeUpdate(_BLBaseModel):
    full_name: str | None = None
    birthdate: _BLDate | None = None
    sex: str | None = None
    address: str | None = None
    contact_number: str | None = None
    civil_status: str | None = None
    special_needs: list | None = None
    emergency_contact: str | None = None
    guardian_evacuee_id: int | None = None
    home_barangay: str | None = None


class BLCenterUpdate(_BLBaseModel):
    name: str | None = None
    address: str | None = None
    capacity: int | None = None


def _bl_can_edit(user, barangay_id):
    return user.role == "city_admin" or (
        barangay_id is not None and user.barangay_id == barangay_id
    )


async def _bl_notify(barangay_id):
    try:
        await manager.broadcast({"type": "records_update", "barangay_id": barangay_id})
    except Exception:  # noqa: S110
        pass


def _bl_evacuee_dict(e):
    return {
        "id": e.id,
        "full_name": e.full_name,
        "birthdate": str(e.birthdate) if e.birthdate is not None else None,
        "sex": e.sex,
        "address": e.address,
        "contact_number": e.contact_number,
        "registered_barangay_id": e.registered_barangay_id,
        "identification_method": e.identification_method,
        "household_id": e.household_id,
        "is_head_of_family": e.is_head_of_family,
        "civil_status": getattr(e, "civil_status", None),
        "special_needs": [x for x in (getattr(e, "special_needs", None) or "").split(",") if x],
        "emergency_contact": getattr(e, "emergency_contact", None),
        "guardian_evacuee_id": getattr(e, "guardian_evacuee_id", None),
        "home_barangay": getattr(e, "home_barangay", None),
    }


def _bl_occupancy(db, center_id):
    return len(_get_current_evacuees_at_center(db, center_id))


@app.put("/evacuees/{evacuee_id}")
async def bl_update_evacuee(
    evacuee_id: int,
    payload: BLEvacueeUpdate,
    db: _BLSession = _BLDepends(get_db),
    user=_BLDepends(auth.get_current_user),
):
    Evacuee = _bl_model("evacuees")
    e = db.query(Evacuee).filter(Evacuee.id == evacuee_id).first()
    if not e:
        raise _BLHTTPException(status_code=404, detail="Evacuee not found.")
    if not _bl_can_edit(user, e.registered_barangay_id):
        raise _BLHTTPException(
            status_code=403, detail="You can only edit residents of your own barangay."
        )
    data = payload.model_dump(exclude_unset=True)
    if "full_name" in data and not (data["full_name"] or "").strip():
        raise _BLHTTPException(status_code=422, detail="Full name cannot be empty.")
    birth_is_text = isinstance(Evacuee.birthdate.property.columns[0].type, _BLString)
    for key, value in data.items():
        if key == "birthdate" and value is not None and birth_is_text:
            value = value.isoformat()
        if key == "special_needs":
            value = (
                ",".join(sorted({str(x).strip() for x in (value or []) if str(x).strip()})) or None
            )
        if isinstance(value, str):
            value = value.strip()
        setattr(e, key, value)
    db.commit()
    db.refresh(e)
    await _bl_notify(e.registered_barangay_id)
    return _bl_evacuee_dict(e)


@app.delete("/evacuees/{evacuee_id}")
async def bl_delete_evacuee(
    evacuee_id: int, db: _BLSession = _BLDepends(get_db), user=_BLDepends(auth.get_current_user)
):
    Evacuee = _bl_model("evacuees")
    e = db.query(Evacuee).filter(Evacuee.id == evacuee_id).first()
    if not e:
        raise _BLHTTPException(status_code=404, detail="Evacuee not found.")
    if not _bl_can_edit(user, e.registered_barangay_id):
        raise _BLHTTPException(
            status_code=403, detail="You can only delete residents of your own barangay."
        )
    Tracker = _bl_model("trackers")
    Household = _bl_model("households")
    Transfer = _bl_model("transfers")
    Checkin = _bl_model("checkin_records")
    db.query(Tracker).filter(Tracker.assigned_evacuee_id == e.id).update(
        {Tracker.assigned_evacuee_id: None}, synchronize_session=False
    )
    db.query(Household).filter(Household.head_of_family_evacuee_id == e.id).update(
        {Household.head_of_family_evacuee_id: None}, synchronize_session=False
    )
    db.query(Evacuee).filter(Evacuee.guardian_evacuee_id == e.id).update(
        {Evacuee.guardian_evacuee_id: None}, synchronize_session=False
    )
    db.query(Transfer).filter(Transfer.evacuee_id == e.id).delete(synchronize_session=False)
    db.query(Checkin).filter(Checkin.evacuee_id == e.id).delete(synchronize_session=False)
    barangay_id = e.registered_barangay_id
    db.delete(e)
    db.commit()
    _bl_remove_photo(evacuee_id)
    await _bl_notify(barangay_id)
    return {"deleted": evacuee_id}


@app.put("/evacuation_centers/{center_id}")
async def bl_update_center(
    center_id: int,
    payload: BLCenterUpdate,
    db: _BLSession = _BLDepends(get_db),
    user=_BLDepends(auth.get_current_user),
):
    Center = _bl_model("evacuation_centers")
    c = db.query(Center).filter(Center.id == center_id).first()
    if not c:
        raise _BLHTTPException(status_code=404, detail="Evacuation center not found.")
    import approvals

    if not approvals.is_it_admin(user):
        raise _BLHTTPException(
            status_code=403,
            detail="Changes to evacuation centers need approval. Send an edit request to the City Hall IT Administrator.",
        )
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and not (data["name"] or "").strip():
        raise _BLHTTPException(status_code=422, detail="Center name cannot be empty.")
    if "capacity" in data:
        if data["capacity"] is None or data["capacity"] < 1:
            raise _BLHTTPException(status_code=422, detail="Capacity must be at least 1.")
        occ = _bl_occupancy(db, c.id)
        if data["capacity"] < occ:
            raise _BLHTTPException(
                status_code=409,
                detail="Capacity cannot be lower than the %d evacuees inside right now." % occ,
            )
    for key, value in data.items():
        setattr(c, key, value.strip() if isinstance(value, str) else value)
    db.commit()
    db.refresh(c)
    await _bl_notify(c.barangay_id)
    return {
        "id": c.id,
        "name": c.name,
        "address": c.address,
        "capacity": c.capacity,
        "barangay_id": c.barangay_id,
    }


@app.delete("/evacuation_centers/{center_id}")
async def bl_delete_center(
    center_id: int, db: _BLSession = _BLDepends(get_db), user=_BLDepends(auth.get_current_user)
):
    Center = _bl_model("evacuation_centers")
    c = db.query(Center).filter(Center.id == center_id).first()
    if not c:
        raise _BLHTTPException(status_code=404, detail="Evacuation center not found.")
    import approvals

    if not approvals.is_it_admin(user):
        raise _BLHTTPException(
            status_code=403,
            detail="Deleting an evacuation center needs approval. Send a delete request to the City Hall IT Administrator.",
        )
    occ = _bl_occupancy(db, c.id)
    if occ > 0:
        raise _BLHTTPException(
            status_code=409,
            detail="%d evacuees are inside this center. Move them to another center before deleting it."
            % occ,
        )
    Checkin = _bl_model("checkin_records")
    Transfer = _bl_model("transfers")
    used = db.query(Checkin).filter(Checkin.evacuation_center_id == c.id).first() is not None
    used = (
        used
        or db.query(Transfer)
        .filter((Transfer.from_center_id == c.id) | (Transfer.to_center_id == c.id))
        .first()
        is not None
    )
    try:
        Ping = _bl_model("tracker_pings")
        used = used or db.query(Ping).filter(Ping.evacuation_center_id == c.id).first() is not None
    except RuntimeError:
        pass
    if used:
        raise _BLHTTPException(
            status_code=409,
            detail="This center has check-in history, so it is kept for the records and cannot be deleted.",
        )
    barangay_id = c.barangay_id
    db.delete(c)
    db.commit()
    await _bl_notify(barangay_id)
    return {"deleted": center_id}


# ---- BilisLikas 2.0: incidents and barangay edit/delete (batch 3) ----
from datetime import datetime as _BL3dt

from sqlalchemy import func as _BL3func

BL_DISASTERS = ["Fire", "Earthquake", "Flood", "Typhoon", "Landslide", "Other"]


class BLIncidentStart(_BLBaseModel):
    disaster_type: str
    evacuation_center_id: int | None = None
    barangay_id: int | None = None


class BLIncidentEnd(_BLBaseModel):
    finish: bool = False


class BLBarangayUpdate(_BLBaseModel):
    name: str


def _bl_iso(dt):
    return dt.isoformat() if dt is not None else None


def _bl_incident_dict(i):
    return {
        "id": i.id,
        "barangay_id": i.barangay_id,
        "evacuation_center_id": i.evacuation_center_id,
        "disaster_type": i.disaster_type,
        "started_at": _bl_iso(i.started_at),
        "ended_at": _bl_iso(i.ended_at),
        "started_by": i.started_by,
        "ended_by": i.ended_by,
        "active": i.ended_at is None,
        "finished": bool(getattr(i, "finished", False)),
        "active_seconds": models.incident_active_seconds(i),
    }


@app.get("/incidents")
def bl_list_incidents(
    active: bool = False,
    db: _BLSession = _BLDepends(get_db),
    user=_BLDepends(auth.get_current_user),
):
    Incident = _bl_model("incidents")
    q = db.query(Incident)
    if user.role != "city_admin":
        q = q.filter(Incident.barangay_id == user.barangay_id)
    if active:
        q = q.filter(Incident.ended_at.is_(None))
    return [_bl_incident_dict(i) for i in q.order_by(Incident.id.desc()).limit(50).all()]


@app.post("/incidents")
async def bl_start_incident(
    payload: BLIncidentStart,
    db: _BLSession = _BLDepends(get_db),
    user=_BLDepends(auth.get_current_user),
):
    Incident = _bl_model("incidents")
    brgy_id = payload.barangay_id if user.role == "city_admin" else user.barangay_id
    if brgy_id is None:
        raise _BLHTTPException(status_code=422, detail="Choose which barangay is evacuating.")
    if db.query(_bl_model("barangays")).filter_by(id=brgy_id).first() is None:
        raise _BLHTTPException(status_code=404, detail="Barangay not found.")
    kind = (payload.disaster_type or "").strip().capitalize()
    if kind not in BL_DISASTERS:
        raise _BLHTTPException(
            status_code=422, detail="Disaster type must be one of: " + ", ".join(BL_DISASTERS) + "."
        )
    if (
        payload.evacuation_center_id is not None
        and db.query(_bl_model("evacuation_centers"))
        .filter_by(id=payload.evacuation_center_id)
        .first()
        is None
    ):
        raise _BLHTTPException(status_code=404, detail="Evacuation center not found.")
    if (
        db.query(Incident)
        .filter(Incident.barangay_id == brgy_id, Incident.ended_at.is_(None))
        .first()
    ):
        raise _BLHTTPException(
            status_code=409,
            detail="An evacuation is already active for this barangay. End it before starting a new one.",
        )
    _now = _BL3dt.utcnow()
    i = Incident(
        barangay_id=brgy_id,
        evacuation_center_id=payload.evacuation_center_id,
        disaster_type=kind,
        started_at=_now,
        started_by=user.id,
        active_seconds=0,
        resumed_at=_now,
    )
    db.add(i)
    db.commit()
    db.refresh(i)
    await _bl_notify(brgy_id)
    return _bl_incident_dict(i)


@app.post("/incidents/{incident_id}/end")
async def bl_end_incident(
    incident_id: int,
    payload: BLIncidentEnd | None = None,
    db: _BLSession = _BLDepends(get_db),
    user=_BLDepends(auth.get_current_user),
):
    Incident = _bl_model("incidents")
    i = db.query(Incident).filter(Incident.id == incident_id).first()
    if not i:
        raise _BLHTTPException(status_code=404, detail="Evacuation not found.")
    if not _bl_can_edit(user, i.barangay_id):
        raise _BLHTTPException(
            status_code=403, detail="You can only end your own barangay's evacuation."
        )
    if i.ended_at is not None:
        raise _BLHTTPException(status_code=409, detail="This evacuation has already ended.")
    now = _BL3dt.utcnow()
    i.active_seconds = models.incident_active_seconds(
        i, now
    )  # add the time since start or last resume
    i.ended_at = now
    i.ended_by = user.id
    if payload is not None and payload.finish:
        # Finished for good: everyone still inside is checked out, so the next evacuation starts from zero.
        # Their check-in records stay in each evacuee's movement history.
        i.finished = True
        Center = _bl_model("evacuation_centers")
        Evacuee = _bl_model("evacuees")
        Checkin = _bl_model("checkin_records")
        ids = {}
        for c in db.query(Center).filter(Center.barangay_id == i.barangay_id).all():
            for e in _get_current_evacuees_at_center(db, c.id):
                ids[e.id] = c.id
        for e in db.query(Evacuee).filter(Evacuee.registered_barangay_id == i.barangay_id).all():
            last = (
                db.query(Checkin)
                .filter(Checkin.evacuee_id == e.id)
                .order_by(Checkin.id.desc())
                .first()
            )
            if last is not None and last.event_type == "check_in":
                ids.setdefault(e.id, last.evacuation_center_id)
        for ev_id, center_id in ids.items():
            db.add(
                Checkin(
                    evacuee_id=ev_id,
                    evacuation_center_id=center_id,
                    event_type="check_out",
                    timestamp=now,
                )
            )
    db.commit()
    db.refresh(i)
    await _bl_notify(i.barangay_id)
    return _bl_incident_dict(i)


@app.post("/incidents/{incident_id}/resume")
async def bl_resume_incident(
    incident_id: int, db: _BLSession = _BLDepends(get_db), user=_BLDepends(auth.get_current_user)
):
    Incident = _bl_model("incidents")
    i = db.query(Incident).filter(Incident.id == incident_id).first()
    if not i:
        raise _BLHTTPException(status_code=404, detail="Evacuation not found.")
    if not _bl_can_edit(user, i.barangay_id):
        raise _BLHTTPException(
            status_code=403, detail="You can only resume your own barangay's evacuation."
        )
    if i.ended_at is None:
        raise _BLHTTPException(status_code=409, detail="This evacuation is still active.")
    if getattr(i, "finished", False):
        raise _BLHTTPException(
            status_code=409,
            detail="This evacuation was finished and cannot be resumed. Start a new evacuation instead.",
        )
    if (
        db.query(Incident)
        .filter(Incident.barangay_id == i.barangay_id, Incident.ended_at.is_(None))
        .first()
    ):
        raise _BLHTTPException(
            status_code=409, detail="Another evacuation is already active for this barangay."
        )
    latest = (
        db.query(Incident)
        .filter(Incident.barangay_id == i.barangay_id)
        .order_by(Incident.id.desc())
        .first()
    )
    if latest.id != i.id:
        raise _BLHTTPException(
            status_code=409, detail="Only the most recent evacuation can be resumed."
        )
    if getattr(i, "active_seconds", None) is None:  # older record: count its first running period
        i.active_seconds = int((i.ended_at - i.started_at).total_seconds())
    i.resumed_at = _BL3dt.utcnow()
    i.ended_at = None
    i.ended_by = None
    db.commit()
    db.refresh(i)
    await _bl_notify(i.barangay_id)
    return _bl_incident_dict(i)


@app.put("/barangays/{barangay_id}")
async def bl_update_barangay(
    barangay_id: int,
    payload: BLBarangayUpdate,
    db: _BLSession = _BLDepends(get_db),
    user=_BLDepends(auth.get_current_user),
):
    Barangay = _bl_model("barangays")
    b = db.query(Barangay).filter(Barangay.id == barangay_id).first()
    if not b:
        raise _BLHTTPException(status_code=404, detail="Barangay not found.")
    if not _bl_can_edit(user, barangay_id):
        raise _BLHTTPException(status_code=403, detail="You can only edit your own barangay.")
    name = (payload.name or "").strip()
    if not name:
        raise _BLHTTPException(status_code=422, detail="Barangay name cannot be empty.")
    clash = (
        db.query(Barangay)
        .filter(_BL3func.lower(Barangay.name) == name.lower(), Barangay.id != barangay_id)
        .first()
    )
    if clash:
        raise _BLHTTPException(status_code=409, detail="Another barangay already uses this name.")
    b.name = name
    db.commit()
    await _bl_notify(barangay_id)
    return {"id": b.id, "name": b.name}


@app.delete("/barangays/{barangay_id}")
async def bl_delete_barangay(
    barangay_id: int, db: _BLSession = _BLDepends(get_db), user=_BLDepends(auth.get_current_user)
):
    if user.role != "city_admin":
        raise _BLHTTPException(status_code=403, detail="Only the City Admin can delete a barangay.")
    Barangay = _bl_model("barangays")
    b = db.query(Barangay).filter(Barangay.id == barangay_id).first()
    if not b:
        raise _BLHTTPException(status_code=404, detail="Barangay not found.")
    links = [
        ("evacuation centers", _bl_model("evacuation_centers"), "barangay_id"),
        ("registered evacuees", _bl_model("evacuees"), "registered_barangay_id"),
        ("user accounts", _bl_model("users"), "barangay_id"),
        ("households", _bl_model("households"), "registered_barangay_id"),
        ("evacuation records", _bl_model("incidents"), "barangay_id"),
    ]
    found = []
    for label, M, col in links:
        n = db.query(M).filter(getattr(M, col) == barangay_id).count()
        if n:
            found.append("%d %s" % (n, label))
    if found:
        raise _BLHTTPException(
            status_code=409,
            detail="This barangay still has " + ", ".join(found) + ". Remove or move them first.",
        )
    db.delete(b)
    db.commit()
    return {"deleted": barangay_id}


# ---- BilisLikas 2.0: pre-registration with webcam photos (batch 4) ----
class BLFaceImages(_BLBaseModel):
    images: list
    angles: list | None = None


class BLMemberCreate(_BLBaseModel):
    full_name: str
    birthdate: _BLDate
    sex: str
    address: str
    contact_number: str | None = None
    civil_status: str | None = None
    special_needs: list | None = None
    emergency_contact: str | None = None


@app.post("/faces/encode")
def bl_faces_encode(payload: BLFaceImages, user=_BLDepends(auth.get_current_user)):
    """Checks each photo for exactly one face and returns their averaged face signature.
    Plain def (not async), so FastAPI runs the slow face math in a worker thread."""
    import base64
    import io

    import numpy as np
    from PIL import Image

    try:
        import face_recognition
    except ImportError:
        raise _BLHTTPException(  # noqa: B904
            status_code=503, detail="Face recognition is not installed on the server."
        )
    images = payload.images or []
    if not 1 <= len(images) <= 5:
        raise _BLHTTPException(status_code=422, detail="Send between 1 and 5 photos.")
    angles = payload.angles or []
    photos, encodings = [], []
    for idx, data in enumerate(images):
        label = str(angles[idx]) if idx < len(angles) else "photo %d" % (idx + 1)
        try:
            raw = data.split(",", 1)[1] if str(data).startswith("data:") else data
            img = Image.open(io.BytesIO(base64.b64decode(raw))).convert("RGB")
        except Exception:
            photos.append(
                {
                    "angle": label,
                    "ok": False,
                    "message": "The " + label + " photo could not be read. Retake it.",
                }
            )
            continue
        arr = np.array(img)
        locs = face_recognition.face_locations(arr, number_of_times_to_upsample=1, model="hog")
        if not locs:
            photos.append(
                {
                    "angle": label,
                    "ok": False,
                    "message": "No face found in the "
                    + label
                    + " photo. Face the light, remove caps or sunglasses, and turn the head a little less.",
                }
            )
            continue
        if len(locs) > 1:
            photos.append(
                {
                    "angle": label,
                    "ok": False,
                    "message": "More than one face in the "
                    + label
                    + " photo. Only the evacuee should be in view.",
                }
            )
            continue
        encodings.append(
            face_recognition.face_encodings(arr, known_face_locations=locs, num_jitters=1)[0]
        )
        photos.append(
            {"angle": label, "ok": True, "message": "Face found in the " + label + " photo."}
        )
    ok = len(encodings) == len(images)
    worst = 0.0
    if ok and len(encodings) > 1:
        worst = max(
            float(np.linalg.norm(a - b))
            for i, a in enumerate(encodings)
            for b in encodings[i + 1 :]
        )
        if worst > 0.6:
            ok = False
            photos.append(
                {
                    "angle": "all",
                    "ok": False,
                    "message": "The photos do not look like the same person. Retake all three.",
                }
            )
    return {
        "ok": ok,
        "photos": photos,
        "max_distance": round(worst, 3),
        "embedding": [float(x) for x in np.mean(encodings, axis=0)] if ok else None,
    }


@app.post("/households/{household_id}/members")
async def bl_add_member(
    household_id: int,
    payload: BLMemberCreate,
    db: _BLSession = _BLDepends(get_db),
    user=_BLDepends(auth.get_current_user),
):
    Household = _bl_model("households")
    Evacuee = _bl_model("evacuees")
    h = db.query(Household).filter(Household.id == household_id).first()
    if not h:
        raise _BLHTTPException(status_code=404, detail="Household not found.")
    if not _bl_can_edit(user, h.registered_barangay_id):
        raise _BLHTTPException(
            status_code=403, detail="You can only add members to your own barangay's households."
        )
    if not payload.full_name.strip() or not payload.address.strip() or not payload.sex.strip():
        raise _BLHTTPException(status_code=422, detail="Full name, sex, and address are required.")
    birth = payload.birthdate
    if isinstance(Evacuee.birthdate.property.columns[0].type, _BLString):
        birth = birth.isoformat()
    needs = (
        ",".join(sorted({str(x).strip() for x in (payload.special_needs or []) if str(x).strip()}))
        or None
    )
    e = Evacuee(
        full_name=payload.full_name.strip(),
        birthdate=birth,
        sex=payload.sex.strip(),
        address=payload.address.strip(),
        contact_number=(payload.contact_number or "").strip() or None,
        registered_barangay_id=h.registered_barangay_id,
        household_id=h.id,
        is_head_of_family=False,
        identification_method="facial_recognition",
        civil_status=payload.civil_status,
        special_needs=needs,
        emergency_contact=payload.emergency_contact,
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    await _bl_notify(h.registered_barangay_id)
    return _bl_evacuee_dict(e)


@app.get("/evacuee_details")
def bl_evacuee_details(db: _BLSession = _BLDepends(get_db), user=_BLDepends(auth.get_current_user)):
    Evacuee = _bl_model("evacuees")
    q = db.query(Evacuee)
    if user.role != "city_admin":
        q = q.filter(Evacuee.registered_barangay_id == user.barangay_id)
    return [
        {
            "id": e.id,
            "civil_status": e.civil_status,
            "emergency_contact": e.emergency_contact,
            "special_needs": [x for x in (e.special_needs or "").split(",") if x],
            "home_barangay": getattr(e, "home_barangay", None),
            "guardian_evacuee_id": getattr(e, "guardian_evacuee_id", None),
        }
        for e in q.all()
    ]


# ---- BilisLikas 2.0: evacuee photos and entrance display (batch 5) ----
import os as _bl_os

from fastapi.responses import FileResponse as _BLFileResponse


class BLPhoto(_BLBaseModel):
    image: str


def _bl_photo_dir():
    d = _bl_os.environ.get("BL_PHOTO_DIR") or _bl_os.path.join(_bl_os.getcwd(), "data", "photos")
    _bl_os.makedirs(d, exist_ok=True)
    return d


def _bl_photo_path(evacuee_id):
    return _bl_os.path.join(_bl_photo_dir(), "%d.jpg" % int(evacuee_id))


def _bl_remove_photo(evacuee_id):
    try:
        _bl_os.remove(_bl_photo_path(evacuee_id))
    except OSError:
        pass


def _bl_short_name(full_name):
    parts = [p for p in (full_name or "").replace(",", " ").split() if p]
    suffixes = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "v"}
    while len(parts) > 1 and parts[-1].lower() in suffixes:
        parts.pop()
    if not parts:
        return "Evacuee"
    if len(parts) == 1:
        return parts[0]
    return parts[0] + " " + parts[-1][0].upper() + "."


def _bl_age(birthdate):
    try:
        y, m, d = [int(x) for x in str(birthdate)[:10].split("-")]
        t = _BL3dt.utcnow()
        return t.year - y - ((t.month, t.day) < (m, d))
    except Exception:
        return None


@app.post("/evacuees/{evacuee_id}/photo")
def bl_save_photo(
    evacuee_id: int,
    payload: BLPhoto,
    db: _BLSession = _BLDepends(get_db),
    user=_BLDepends(auth.get_current_user),
):
    import base64
    import io

    from PIL import Image

    Evacuee = _bl_model("evacuees")
    e = db.query(Evacuee).filter(Evacuee.id == evacuee_id).first()
    if not e:
        raise _BLHTTPException(status_code=404, detail="Evacuee not found.")
    if not _bl_can_edit(user, e.registered_barangay_id):
        raise _BLHTTPException(
            status_code=403, detail="You can only add photos for your own barangay."
        )
    try:
        raw = payload.image.split(",", 1)[1] if payload.image.startswith("data:") else payload.image
        img = Image.open(io.BytesIO(base64.b64decode(raw))).convert("RGB")
    except Exception:
        raise _BLHTTPException(status_code=422, detail="The photo could not be read.")  # noqa: B904
    w, h = img.size
    side = min(w, h)
    img = img.crop(
        ((w - side) // 2, (h - side) // 2, (w - side) // 2 + side, (h - side) // 2 + side)
    ).resize((240, 240))
    img.save(_bl_photo_path(e.id), format="JPEG", quality=80)
    return {"saved": True, "evacuee_id": e.id}


@app.get("/evacuees/{evacuee_id}/photo")
def bl_get_photo(
    evacuee_id: int, db: _BLSession = _BLDepends(get_db), user=_BLDepends(auth.get_current_user)
):
    Evacuee = _bl_model("evacuees")
    e = db.query(Evacuee).filter(Evacuee.id == evacuee_id).first()
    if not e:
        raise _BLHTTPException(status_code=404, detail="Evacuee not found.")
    if not _bl_can_edit(user, e.registered_barangay_id):
        raise _BLHTTPException(status_code=403, detail="Not allowed.")
    path = _bl_photo_path(e.id)
    if not _bl_os.path.exists(path):
        raise _BLHTTPException(status_code=404, detail="No photo saved for this evacuee.")
    return _BLFileResponse(
        path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=300"}
    )


@app.get("/display/{center_id}")
def bl_display(
    center_id: int, db: _BLSession = _BLDepends(get_db), user=_BLDepends(auth.get_current_user)
):
    Center = _bl_model("evacuation_centers")
    Evacuee = _bl_model("evacuees")
    Checkin = _bl_model("checkin_records")
    Barangay = _bl_model("barangays")
    Incident = _bl_model("incidents")
    c = db.query(Center).filter(Center.id == center_id).first()
    if not c:
        raise _BLHTTPException(status_code=404, detail="Evacuation center not found.")
    if not _bl_can_edit(user, c.barangay_id):
        raise _BLHTTPException(
            status_code=403, detail="You can only open the display for your own barangay's centers."
        )
    b = db.query(Barangay).filter(Barangay.id == c.barangay_id).first()
    residents = db.query(Evacuee).filter(Evacuee.registered_barangay_id == c.barangay_id).all()

    def latest(ev_id):
        return (
            db.query(Checkin)
            .filter(Checkin.evacuee_id == ev_id)
            .order_by(Checkin.timestamp.desc(), Checkin.id.desc())
            .first()
        )

    waiting, safe = [], 0
    for e in residents:
        r = latest(e.id)
        inside = r is not None and r.event_type == "check_in"
        if inside:
            safe += 1
            continue
        tags = []
        needs = [x for x in (getattr(e, "special_needs", None) or "").split(",") if x]
        age = _bl_age(e.birthdate)
        if "Senior citizen" in needs or (age is not None and age >= 60):
            tags.append("Senior")
        if "PWD" in needs:
            tags.append("PWD")
        if "Pregnant" in needs:
            tags.append("Pregnant")
        if age is not None and age < 5:
            tags.append("Child under 5")
        if any(x.startswith("Medical") for x in needs):
            tags.append("Medical")
        waiting.append(
            {
                "id": e.id,
                "name": _bl_short_name(e.full_name),
                "tags": tags,
                "has_photo": _bl_os.path.exists(_bl_photo_path(e.id)),
            }
        )
    waiting.sort(key=lambda w: (0 if w["tags"] else 1, w["name"].lower()))

    arrived = []
    here_ids = set()
    for r in (
        db.query(Checkin)
        .filter(Checkin.evacuation_center_id == c.id, Checkin.event_type == "check_in")
        .order_by(Checkin.timestamp.desc(), Checkin.id.desc())
        .limit(200)
        .all()
    ):
        if r.evacuee_id in here_ids:
            continue
        cur = latest(r.evacuee_id)
        if cur is None or cur.id != r.id:
            continue
        here_ids.add(r.evacuee_id)
        e = db.query(Evacuee).filter(Evacuee.id == r.evacuee_id).first()
        if e is None:
            continue
        arrived.append(
            {
                "id": e.id,
                "name": _bl_short_name(e.full_name),
                "time": _bl_iso(r.timestamp),
                "has_photo": _bl_os.path.exists(_bl_photo_path(e.id)),
            }
        )
        if len(arrived) >= 12:
            break
    inc = (
        db.query(Incident)
        .filter(Incident.barangay_id == c.barangay_id, Incident.ended_at.is_(None))
        .first()
    )
    return {
        "center": {"id": c.id, "name": c.name, "capacity": c.capacity},
        "barangay": b.name if b else None,
        "incident": _bl_incident_dict(inc) if inc else None,
        "expected_total": len(residents),
        "safe_total": safe,
        "waiting": waiting,
        "arrived": arrived,
    }


# ---- BilisLikas 2.0: barangay self-registration (batch 6) ----
import re as _bl_re

BL_DESIGNATIONS = ["Barangay Chairman", "Barangay Kagawad", "SK Chairman", "Barangay Secretary"]


class BLRegister(_BLBaseModel):
    barangay_name: str
    designation: str
    designation_other: str | None = None
    full_name: str
    email: str
    mobile_number: str
    password: str
    registration_code: str | None = None
    district: str | None = None
    zone: str | None = None
    employee_id: str | None = None
    evacuation_centers: list | None = None


def _bl_required_code():
    return (_bl_os.environ.get("REGISTRATION_CODE") or "").strip()


@app.get("/register/config")
def bl_register_config():
    return {"code_required": bool(_bl_required_code()), "designations": BL_DESIGNATIONS}


@app.post("/register", status_code=201)
async def bl_register(payload: BLRegister, db: _BLSession = _BLDepends(get_db)):
    code = _bl_required_code()
    if code and (payload.registration_code or "").strip() != code:
        raise _BLHTTPException(
            status_code=403,
            detail="The registration code is not correct. Ask the City DRRMO for it.",
        )
    name = " ".join((payload.barangay_name or "").split())
    person = " ".join((payload.full_name or "").split())
    email = (payload.email or "").strip().lower()
    if not name:
        raise _BLHTTPException(status_code=422, detail="Enter the barangay name.")
    if not person:
        raise _BLHTTPException(status_code=422, detail="Enter your full name.")
    if not _bl_re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise _BLHTTPException(status_code=422, detail="Enter a valid email address.")
    designation = (payload.designation or "").strip()
    if designation not in BL_DESIGNATIONS:
        designation = " ".join((payload.designation_other or "").split())
        if not designation:
            raise _BLHTTPException(
                status_code=422, detail="Choose your designation, or type it under Others."
            )
    digits = _bl_re.sub(r"\D", "", payload.mobile_number or "")
    if digits.startswith("63"):
        digits = "0" + digits[2:]
    if len(digits) == 10 and digits.startswith("9"):
        digits = "0" + digits
    if not _bl_re.fullmatch(r"09\d{9}", digits):
        raise _BLHTTPException(
            status_code=422, detail="Enter a valid Philippine mobile number, such as 0917 123 4567."
        )
    pw = payload.password or ""
    if len(pw) < 8 or not _bl_re.search(r"[A-Za-z]", pw) or not _bl_re.search(r"\d", pw):
        raise _BLHTTPException(
            status_code=422,
            detail="Use a password with at least 8 characters, including letters and a number.",
        )
    emp = " ".join((payload.employee_id or "").split())
    if len(emp) < 3:
        raise _BLHTTPException(status_code=422, detail="Enter your barangay employee ID number.")
    User = models.User
    Barangay = _bl_model("barangays")
    taken = (
        db.query(User).filter(_BL3func.lower(User.email) == email).first()
        or db.query(User).filter(_BL3func.lower(User.username) == email).first()
    )
    if taken:
        raise _BLHTTPException(
            status_code=409, detail="An account with this email already exists. Sign in instead."
        )
    b = db.query(Barangay).filter(_BL3func.lower(Barangay.name) == name.lower()).first()
    created = False
    if b is None:
        b = Barangay(
            name=name, district=payload.district if payload.district in MANILA_DISTRICTS else None
        )
        db.add(b)
        db.flush()
        created = True
    elif not getattr(b, "district", None) and payload.district in MANILA_DISTRICTS:
        b.district = payload.district
    if (payload.zone or "").strip():
        from sqlalchemy import text as _zt

        import barangay_info as _bz

        db.execute(
            _zt("UPDATE barangays SET zone = COALESCE(zone, :z) WHERE id = :i"),
            {"z": _bz.clean_zone(payload.zone), "i": b.id},
        )
    u = User(
        username=email,
        email=email,
        password_hash=auth.get_password_hash(pw),
        role="barangay_official",
        barangay_id=b.id,
        full_name=person,
        designation=designation,
        mobile_number=digits,
        employee_id=emp,
        account_status="pending",
    )
    db.add(u)
    new_center_ids = []
    Center = _bl_model("evacuation_centers")
    added = 0
    for c in payload.evacuation_centers or []:
        try:
            cname = " ".join(str(c.get("name") or "").split())
            caddr = " ".join(str(c.get("address") or "").split())
            ccap = int(c.get("capacity") or 0)
        except AttributeError, TypeError, ValueError:
            continue
        if not cname or not caddr or ccap <= 0:
            raise _BLHTTPException(
                status_code=422,
                detail="Each evacuation center needs a name, an address and a capacity.",
            )
        if (
            db.query(Center)
            .filter(Center.barangay_id == b.id, _BL3func.lower(Center.name) == cname.lower())
            .first()
        ):
            continue
        nc = Center(name=cname, address=caddr, capacity=ccap, barangay_id=b.id)
        db.add(nc)
        db.flush()
        new_center_ids.append(nc.id)
        added += 1
    db.flush()
    import approvals

    approvals.remember_signup(db, u.id, b.id, created, new_center_ids)
    db.commit()
    return {
        "id": u.id,
        "email": email,
        "barangay_id": b.id,
        "barangay": b.name,
        "new_barangay": created,
        "centers_added": added,
        "status": "pending",
    }


# ---- BilisLikas 2.0: cloud sync phase 1 (sync-ready records) ----
@app.get("/sync/status")
def sync_status(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    counts = {}
    for cls in models.SYNCED_MODELS:
        counts[cls.__tablename__] = {
            "records": db.query(cls).count(),
            "missing_uuid": db.query(cls).filter(cls.uuid.is_(None)).count(),
        }
    state = {r.key: r.value for r in db.query(models.SyncState).all()}
    return {
        "server_id": models.SERVER_ID,
        "tables": counts,
        "tombstones": db.query(models.SyncTombstone).count(),
        "sync_state": state,
    }


# ---- BilisLikas 2.0: cloud sync phase 3 (push, pull, notify) ----
import os as _sync_os

from fastapi import Header as _SyncHeader
from pydantic import BaseModel as _SyncBase

import sync_core


class SyncPushIn(_SyncBase):
    server_id: str
    rows: list = []
    tombstones: list = []


def _sync_check_key(key):
    expected = (_sync_os.getenv("SYNC_KEY") or "").strip()
    if not expected:
        raise HTTPException(
            status_code=503, detail="Sync is not configured on this server (SYNC_KEY missing)."
        )
    if (key or "").strip() != expected:
        raise HTTPException(status_code=401, detail="Invalid sync key.")


@app.post("/sync/push")
def sync_push(
    payload: SyncPushIn, db: Session = Depends(get_db), x_sync_key: str = _SyncHeader(None)
):
    """Cloud hub: receive changes from one barangay server."""
    _sync_check_key(x_sync_key)
    applied, skipped, aliased, waiting = sync_core.apply_rows(db, payload.rows)
    removed = sync_core.apply_tombstones(db, payload.tombstones)
    for table, uuid in applied:
        db.add(
            models.SyncLog(
                table_name=table, record_uuid=uuid, is_tombstone=False, origin=payload.server_id
            )
        )
    for t in payload.tombstones:
        if t.get("table") in sync_core.BY_TABLE and t.get("uuid"):
            db.add(
                models.SyncLog(
                    table_name=t["table"],
                    record_uuid=t["uuid"],
                    is_tombstone=True,
                    origin=payload.server_id,
                )
            )
    db.commit()
    db.info.pop("sync_import", None)
    return {
        "applied": [u for _t, u in applied],
        "skipped": skipped,
        "aliased": aliased,
        "waiting": waiting,
        "removed": [u for _t, u in removed],
    }


@app.get("/sync/pull")
def sync_pull(
    since: int = 0,
    exclude_origin: str = "",
    limit: int = 300,
    db: Session = Depends(get_db),
    x_sync_key: str = _SyncHeader(None),
):
    """Cloud hub: changes from all other servers since the given position."""
    _sync_check_key(x_sync_key)
    q = db.query(models.SyncLog).filter(models.SyncLog.seq > since)
    if exclude_origin:
        q = q.filter(models.SyncLog.origin != exclude_origin)
    entries = q.order_by(models.SyncLog.seq).limit(max(1, min(limit, 1000))).all()
    latest = {}
    for (
        e
    ) in entries:  # keep only the newest entry for each record (a deletion beats an older update)
        latest[e.record_uuid] = e
    rows, tombstones, cache = [], [], {}
    for e in sorted(latest.values(), key=lambda x: x.seq):
        if e.is_tombstone:
            tombstones.append({"table": e.table_name, "uuid": e.record_uuid})
            continue
        cls = sync_core.BY_TABLE.get(e.table_name, (None,))[0]
        obj = db.query(cls).filter(cls.uuid == e.record_uuid).first() if cls else None
        if obj is not None:
            rows.append(sync_core.serialize(db, obj, cache))
    last = db.query(func.max(models.SyncLog.seq)).scalar() or 0
    nxt = entries[-1].seq if entries else since
    return {
        "rows": rows,
        "tombstones": tombstones,
        "next": nxt,
        "more": nxt < last and len(entries) > 0,
    }


@app.post("/sync/notify")
async def sync_notify(x_sync_key: str = _SyncHeader(None), db: Session = Depends(get_db)):
    """Local server: the sync agent calls this after applying new data, so open pages refresh."""
    _sync_check_key(x_sync_key)
    for b in db.query(models.Barangay).all():
        await manager.broadcast({"type": "sync_update", "barangay_id": b.id})
    return {"ok": True}


# ---- BilisLikas 2.0: cloud sync phase 4 (status and districts) ----
MANILA_DISTRICTS = [
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


class BLDistrict(_BLBaseModel):
    district: str | None = None


@app.get("/districts")
def list_districts():
    return MANILA_DISTRICTS


@app.put("/barangays/{barangay_id}/district")
async def set_barangay_district(
    barangay_id: int,
    payload: BLDistrict,
    db: Session = Depends(get_db),
    current_user=Depends(auth.get_current_user),
):
    if current_user.role != "city_admin":
        raise HTTPException(
            status_code=403, detail="Only the City Admin can set a barangay's district."
        )
    b = db.query(models.Barangay).filter(models.Barangay.id == barangay_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Barangay not found.")
    d = (payload.district or "").strip() or None
    if d is not None and d not in MANILA_DISTRICTS:
        raise HTTPException(status_code=422, detail="Choose one of the 16 districts of Manila.")
    b.district = d
    db.commit()
    await _bl_notify(barangay_id)
    return {"id": b.id, "name": b.name, "district": b.district}


@app.get("/sync/info")
def sync_info(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    """Small summary for the sidebar badge."""
    st = {r.key: r.value for r in db.query(models.SyncState).all()}
    hub_rows = (
        db.query(
            models.SyncLog.origin,
            func.max(models.SyncLog.received_at),
            func.count(models.SyncLog.seq),
        )
        .group_by(models.SyncLog.origin)
        .all()
    )
    if hub_rows:  # this server receives data from others: it is the cloud hub
        return {
            "role": "hub",
            "server_id": models.SERVER_ID,
            "servers": [
                {"server_id": o, "last_received_at": _bl_iso(t), "changes": n}
                for o, t, n in hub_rows
            ],
        }
    waiting = sum(
        db.query(cls).filter(cls.sync_dirty.is_(True)).count() for cls in models.SYNCED_MODELS
    )
    last_t = int(st.get("push_tombstone_id", "0") or 0)
    waiting += db.query(models.SyncTombstone).filter(models.SyncTombstone.id > last_t).count()
    return {
        "role": "server",
        "server_id": models.SERVER_ID,
        "configured": bool(st.get("last_pull_at")),
        "last_push_at": st.get("last_push_at"),
        "last_pull_at": st.get("last_pull_at"),
        "waiting": waiting,
    }


# ---- BilisLikas 2.0: families, infants, home barangay ----
import families

app.include_router(families.router)

# ---- BilisLikas 2.0: forgot password ----
import password_reset

app.include_router(password_reset.router)

import admin_auth

app.include_router(admin_auth.router)

import resident

app.include_router(resident.router)


# no-cache for app pages: browsers always check for updated HTML and JS
@app.middleware("http")
async def _bl_no_cache(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/app/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


import barangay_info

app.include_router(barangay_info.router)

import relief

app.include_router(relief.router)

import center_delete

app.include_router(center_delete.router)

import barangay_delete

app.include_router(barangay_delete.router)

import history

app.include_router(history.router)

app.include_router(login_log.router)

import approvals

app.include_router(approvals.router)

import face_check

app.include_router(face_check.router)

import sms

app.include_router(sms.router)


# ISO/IEC 25010 quality safeguards (security, accountability, reliability, performance)
import iso_quality

iso_quality.install(app)

# ---- BilisLikas 2.0: cross-barangay evacuee tracking ----
import cross_barangay

app.include_router(cross_barangay.router)
