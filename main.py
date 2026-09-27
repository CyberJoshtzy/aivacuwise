from sqlalchemy import or_
import json
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from datetime import datetime
from database import get_db
from fastapi.responses import FileResponse
import models
import schemas
import auth
from connection_manager import manager

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

@app.get("/barangays", response_model=List[schemas.BarangayOut])
def list_barangays(db: Session = Depends(get_db)):
    return db.query(models.Barangay).all()

@app.post("/evacuation_centers", response_model=schemas.EvacuationCenterOut)
def create_center(center: schemas.EvacuationCenterCreate, db: Session = Depends(get_db)):
    db_center = models.EvacuationCenter(**center.model_dump())
    db.add(db_center)
    db.commit()
    db.refresh(db_center)
    return db_center

@app.get("/evacuation_centers", response_model=List[schemas.EvacuationCenterOut])
def list_centers(db: Session = Depends(get_db)):
    return db.query(models.EvacuationCenter).all()

@app.post("/evacuees", response_model=schemas.EvacueeOut)
def register_evacuee(evacuee: schemas.EvacueeCreate, db: Session = Depends(get_db)):
    db_evacuee = models.Evacuee(**evacuee.model_dump())
    db.add(db_evacuee)
    db.commit()
    db.refresh(db_evacuee)
    return db_evacuee

@app.get("/evacuees", response_model=List[schemas.EvacueeOut])
def list_evacuees(db: Session = Depends(get_db)):
    return db.query(models.Evacuee).all()

@app.post("/checkin", response_model=schemas.CheckinOut)
async def checkin_evacuee(record: schemas.CheckinCreate, db: Session = Depends(get_db)):
    evacuee = db.query(models.Evacuee).filter(models.Evacuee.id == record.evacuee_id).first()
    if not evacuee:
        raise HTTPException(status_code=404, detail="Evacuee not found")
    center = db.query(models.EvacuationCenter).filter(models.EvacuationCenter.id == record.evacuation_center_id).first()
    if not center:
        raise HTTPException(status_code=404, detail="Evacuation center not found")
    db_record = models.CheckinRecord(**record.model_dump())
    db.add(db_record)
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
        raise HTTPException(status_code=403, detail="User creation is closed. Ask a city admin to create your account via /admin/users.")
    hashed_password = auth.get_password_hash(user.password)
    db_user = models.User(email=(user.email.strip().lower() if getattr(user, 'email', None) else None), username=user.username, password_hash=hashed_password, role=user.role, barangay_id=user.barangay_id)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@app.post("/admin/users", response_model=schemas.UserOut)
def admin_create_user(user: schemas.UserCreate, current_user: models.User = Depends(auth.require_role("city_admin")), db: Session = Depends(get_db)):
    hashed_password = auth.get_password_hash(user.password)
    db_user = models.User(email=(user.email.strip().lower() if getattr(user, 'email', None) else None), username=user.username, password_hash=hashed_password, role=user.role, barangay_id=user.barangay_id)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@app.post("/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(or_(models.User.username == form_data.username, models.User.email == form_data.username.strip().lower())).first()
    if not user or not auth.verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
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

@app.post("/transfers", response_model=schemas.TransferOut)
async def create_transfer(
    transfer: schemas.TransferCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    evacuee = db.query(models.Evacuee).filter(models.Evacuee.id == transfer.evacuee_id).first()
    if not evacuee:
        raise HTTPException(status_code=404, detail="Evacuee not found")

    to_center = db.query(models.EvacuationCenter).filter(models.EvacuationCenter.id == transfer.to_center_id).first()
    if not to_center:
        raise HTTPException(status_code=404, detail="Destination evacuation center not found")

    from_center = None

    if transfer.from_center_id is not None:
        if transfer.from_center_id == transfer.to_center_id:
            raise HTTPException(status_code=400, detail="Source and destination centers must be different")

        from_center = db.query(models.EvacuationCenter).filter(models.EvacuationCenter.id == transfer.from_center_id).first()
        if not from_center:
            raise HTTPException(status_code=404, detail="Source evacuation center not found")

        latest_event = (
            db.query(models.CheckinRecord)
            .filter(models.CheckinRecord.evacuee_id == transfer.evacuee_id)
            .order_by(models.CheckinRecord.id.desc())
            .first()
        )
        if (
            not latest_event
            or latest_event.event_type != "check_in"
            or latest_event.evacuation_center_id != transfer.from_center_id
        ):
            raise HTTPException(
                status_code=400,
                detail="Evacuee is not currently checked in at the specified source center",
            )

    now = datetime.utcnow()

    db_transfer = models.Transfer(
        evacuee_id=transfer.evacuee_id,
        from_center_id=transfer.from_center_id,
        to_center_id=transfer.to_center_id,
        timestamp=now,
        approved_by=current_user.id,
    )
    db.add(db_transfer)

    if transfer.from_center_id is not None:
        db.add(models.CheckinRecord(
            evacuee_id=transfer.evacuee_id,
            evacuation_center_id=transfer.from_center_id,
            event_type="check_out",
            timestamp=now,
        ))

    db.add(models.CheckinRecord(
        evacuee_id=transfer.evacuee_id,
        evacuation_center_id=transfer.to_center_id,
        event_type="check_in",
        timestamp=now,
    ))

    db.commit()
    db.refresh(db_transfer)

    if from_center is not None:
        await manager.broadcast({"type": "occupancy_update", "barangay_id": from_center.barangay_id})
    await manager.broadcast({"type": "occupancy_update", "barangay_id": to_center.barangay_id})

    return db_transfer


@app.get("/transfers", response_model=List[schemas.TransferOut])
def list_transfers(db: Session = Depends(get_db)):
    return db.query(models.Transfer).order_by(models.Transfer.id.desc()).all()


@app.get("/evacuees/{evacuee_id}/transfers", response_model=List[schemas.TransferOut])
def evacuee_transfer_history(evacuee_id: int, db: Session = Depends(get_db)):
    evacuee = db.query(models.Evacuee).filter(models.Evacuee.id == evacuee_id).first()
    if not evacuee:
        raise HTTPException(status_code=404, detail="Evacuee not found")
    return (
        db.query(models.Transfer)
        .filter(models.Transfer.evacuee_id == evacuee_id)
        .order_by(models.Transfer.id.desc())
        .all()
    )


@app.post("/checkin/walkin", response_model=schemas.WalkinCheckinOut)
async def walkin_register_and_checkin(
    data: schemas.WalkinCheckinCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    center = db.query(models.EvacuationCenter).filter(models.EvacuationCenter.id == data.evacuation_center_id).first()
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


@app.get("/evacuees/{evacuee_id}/history", response_model=List[schemas.CheckinOut])
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
        centers = db.query(models.EvacuationCenter).filter(models.EvacuationCenter.barangay_id == barangay.id).all()
        center_list = []
        for center in centers:
            evacuees = _get_current_evacuees_at_center(db, center.id)
            center_list.append({
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
            })
        barangay_list.append({
            "id": barangay.id,
            "name": barangay.name,
            "centers": center_list,
        })

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
            evacuee = db.query(models.Evacuee).filter(models.Evacuee.id == t.assigned_evacuee_id).first()
            tracker_list.append({
                "tracker_id": t.id,
                "device_id": t.device_id,
                "evacuee_id": t.assigned_evacuee_id,
                "evacuee_name": evacuee.full_name if evacuee else None,
                "latitude": latest_ping.latitude,
                "longitude": latest_ping.longitude,
                "timestamp": latest_ping.timestamp.isoformat(),
            })

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
    barangay = db.query(models.Barangay).filter(models.Barangay.id == household.registered_barangay_id).first()
    if not barangay:
        raise HTTPException(status_code=404, detail="Barangay not found")
    if not household.members:
        raise HTTPException(status_code=400, detail="A household needs at least one member")

    head_count = sum(1 for m in household.members if m.is_head_of_family)
    if head_count > 1:
        raise HTTPException(status_code=400, detail="Only one member can be marked as head of family")

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


@app.get("/barangays/{barangay_id}/households", response_model=List[schemas.HouseholdOut])
def list_households_for_barangay(barangay_id: int, db: Session = Depends(get_db)):
    households = db.query(models.Household).filter(models.Household.registered_barangay_id == barangay_id).all()
    result = []
    for h in households:
        members = db.query(models.Evacuee).filter(models.Evacuee.household_id == h.id).all()
        result.append({
            "id": h.id,
            "registered_barangay_id": h.registered_barangay_id,
            "head_of_family_evacuee_id": h.head_of_family_evacuee_id,
            "created_at": h.created_at,
            "members": members,
        })
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
            center = db.query(models.EvacuationCenter).filter(models.EvacuationCenter.id == latest_event.evacuation_center_id).first()
            if center:
                current_center_id = center.id
                current_center_name = center.name
        statuses.append({
            "evacuee_id": m.id,
            "full_name": m.full_name,
            "is_head_of_family": m.is_head_of_family or False,
            "current_center_id": current_center_id,
            "current_center_name": current_center_name,
        })
    return {"household_id": household_id, "members": statuses}


@app.get("/kiosk")
async def kiosk():
    return FileResponse("static/kiosk.html")


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.post("/evacuees/{evacuee_id}/facial_embedding")
def set_facial_embedding(evacuee_id: int, payload: schemas.FacialEmbeddingIn, db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
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
        except (TypeError, ValueError):
            continue
        result.append({"evacuee_id": e.id, "full_name": e.full_name, "embedding": embedding})
    return result


# ---- BilisLikas 2.0: edit and delete endpoints (batch 2) ----
from datetime import date as _BLDate
from typing import Optional as _BLOptional
from fastapi import Depends as _BLDepends, HTTPException as _BLHTTPException
from pydantic import BaseModel as _BLBaseModel
from sqlalchemy import String as _BLString
from sqlalchemy.orm import Session as _BLSession


def _bl_model(table):
    key = '_' * 2 + 'tablename' + '_' * 2
    for obj in vars(models).values():
        if isinstance(obj, type) and getattr(obj, key, None) == table:
            return obj
    raise RuntimeError('No model found for table ' + table)


class BLEvacueeUpdate(_BLBaseModel):
    full_name: _BLOptional[str] = None
    birthdate: _BLOptional[_BLDate] = None
    sex: _BLOptional[str] = None
    address: _BLOptional[str] = None
    contact_number: _BLOptional[str] = None
    civil_status: _BLOptional[str] = None
    special_needs: _BLOptional[list] = None
    emergency_contact: _BLOptional[str] = None


class BLCenterUpdate(_BLBaseModel):
    name: _BLOptional[str] = None
    address: _BLOptional[str] = None
    capacity: _BLOptional[int] = None


def _bl_can_edit(user, barangay_id):
    return user.role == 'city_admin' or (barangay_id is not None and user.barangay_id == barangay_id)


async def _bl_notify(barangay_id):
    try:
        await manager.broadcast({'type': 'records_update', 'barangay_id': barangay_id})
    except Exception:
        pass


def _bl_evacuee_dict(e):
    return {
        'id': e.id, 'full_name': e.full_name,
        'birthdate': str(e.birthdate) if e.birthdate is not None else None,
        'sex': e.sex, 'address': e.address, 'contact_number': e.contact_number,
        'registered_barangay_id': e.registered_barangay_id,
        'identification_method': e.identification_method,
        'household_id': e.household_id, 'is_head_of_family': e.is_head_of_family,
        'civil_status': getattr(e, 'civil_status', None),
        'special_needs': [x for x in (getattr(e, 'special_needs', None) or '').split(',') if x],
        'emergency_contact': getattr(e, 'emergency_contact', None),
    }


def _bl_occupancy(db, center_id):
    return len(_get_current_evacuees_at_center(db, center_id))


@app.put('/evacuees/{evacuee_id}')
async def bl_update_evacuee(evacuee_id: int, payload: BLEvacueeUpdate,
                            db: _BLSession = _BLDepends(get_db),
                            user=_BLDepends(auth.get_current_user)):
    Evacuee = _bl_model('evacuees')
    e = db.query(Evacuee).filter(Evacuee.id == evacuee_id).first()
    if not e:
        raise _BLHTTPException(status_code=404, detail='Evacuee not found.')
    if not _bl_can_edit(user, e.registered_barangay_id):
        raise _BLHTTPException(status_code=403, detail='You can only edit residents of your own barangay.')
    data = payload.model_dump(exclude_unset=True)
    if 'full_name' in data and not (data['full_name'] or '').strip():
        raise _BLHTTPException(status_code=422, detail='Full name cannot be empty.')
    birth_is_text = isinstance(Evacuee.birthdate.property.columns[0].type, _BLString)
    for key, value in data.items():
        if key == 'birthdate' and value is not None and birth_is_text:
            value = value.isoformat()
        if key == 'special_needs':
            value = ','.join(sorted({str(x).strip() for x in (value or []) if str(x).strip()})) or None
        if isinstance(value, str):
            value = value.strip()
        setattr(e, key, value)
    db.commit()
    db.refresh(e)
    await _bl_notify(e.registered_barangay_id)
    return _bl_evacuee_dict(e)


@app.delete('/evacuees/{evacuee_id}')
async def bl_delete_evacuee(evacuee_id: int,
                            db: _BLSession = _BLDepends(get_db),
                            user=_BLDepends(auth.get_current_user)):
    Evacuee = _bl_model('evacuees')
    e = db.query(Evacuee).filter(Evacuee.id == evacuee_id).first()
    if not e:
        raise _BLHTTPException(status_code=404, detail='Evacuee not found.')
    if not _bl_can_edit(user, e.registered_barangay_id):
        raise _BLHTTPException(status_code=403, detail='You can only delete residents of your own barangay.')
    Tracker = _bl_model('trackers')
    Household = _bl_model('households')
    Transfer = _bl_model('transfers')
    Checkin = _bl_model('checkin_records')
    db.query(Tracker).filter(Tracker.assigned_evacuee_id == e.id).update({Tracker.assigned_evacuee_id: None}, synchronize_session=False)
    db.query(Household).filter(Household.head_of_family_evacuee_id == e.id).update({Household.head_of_family_evacuee_id: None}, synchronize_session=False)
    db.query(Transfer).filter(Transfer.evacuee_id == e.id).delete(synchronize_session=False)
    db.query(Checkin).filter(Checkin.evacuee_id == e.id).delete(synchronize_session=False)
    barangay_id = e.registered_barangay_id
    db.delete(e)
    db.commit()
    await _bl_notify(barangay_id)
    return {'deleted': evacuee_id}


@app.put('/evacuation_centers/{center_id}')
async def bl_update_center(center_id: int, payload: BLCenterUpdate,
                           db: _BLSession = _BLDepends(get_db),
                           user=_BLDepends(auth.get_current_user)):
    Center = _bl_model('evacuation_centers')
    c = db.query(Center).filter(Center.id == center_id).first()
    if not c:
        raise _BLHTTPException(status_code=404, detail='Evacuation center not found.')
    if not _bl_can_edit(user, c.barangay_id):
        raise _BLHTTPException(status_code=403, detail='You can only edit your own barangay\'s centers.')
    data = payload.model_dump(exclude_unset=True)
    if 'name' in data and not (data['name'] or '').strip():
        raise _BLHTTPException(status_code=422, detail='Center name cannot be empty.')
    if 'capacity' in data:
        if data['capacity'] is None or data['capacity'] < 1:
            raise _BLHTTPException(status_code=422, detail='Capacity must be at least 1.')
        occ = _bl_occupancy(db, c.id)
        if data['capacity'] < occ:
            raise _BLHTTPException(status_code=409, detail='Capacity cannot be lower than the %d evacuees inside right now.' % occ)
    for key, value in data.items():
        setattr(c, key, value.strip() if isinstance(value, str) else value)
    db.commit()
    db.refresh(c)
    await _bl_notify(c.barangay_id)
    return {'id': c.id, 'name': c.name, 'address': c.address, 'capacity': c.capacity, 'barangay_id': c.barangay_id}


@app.delete('/evacuation_centers/{center_id}')
async def bl_delete_center(center_id: int,
                           db: _BLSession = _BLDepends(get_db),
                           user=_BLDepends(auth.get_current_user)):
    Center = _bl_model('evacuation_centers')
    c = db.query(Center).filter(Center.id == center_id).first()
    if not c:
        raise _BLHTTPException(status_code=404, detail='Evacuation center not found.')
    if not _bl_can_edit(user, c.barangay_id):
        raise _BLHTTPException(status_code=403, detail='You can only delete your own barangay\'s centers.')
    occ = _bl_occupancy(db, c.id)
    if occ > 0:
        raise _BLHTTPException(status_code=409, detail='%d evacuees are inside this center. Transfer them to another center before deleting it.' % occ)
    Checkin = _bl_model('checkin_records')
    Transfer = _bl_model('transfers')
    used = db.query(Checkin).filter(Checkin.evacuation_center_id == c.id).first() is not None
    used = used or db.query(Transfer).filter((Transfer.from_center_id == c.id) | (Transfer.to_center_id == c.id)).first() is not None
    try:
        Ping = _bl_model('tracker_pings')
        used = used or db.query(Ping).filter(Ping.evacuation_center_id == c.id).first() is not None
    except RuntimeError:
        pass
    if used:
        raise _BLHTTPException(status_code=409, detail='This center has check-in or transfer history, so it is kept for the records and cannot be deleted.')
    barangay_id = c.barangay_id
    db.delete(c)
    db.commit()
    await _bl_notify(barangay_id)
    return {'deleted': center_id}


# ---- BilisLikas 2.0: incidents and barangay edit/delete (batch 3) ----
from datetime import datetime as _BL3dt
from sqlalchemy import func as _BL3func

BL_DISASTERS = ['Fire', 'Earthquake', 'Flood', 'Typhoon', 'Landslide', 'Other']


class BLIncidentStart(_BLBaseModel):
    disaster_type: str
    evacuation_center_id: _BLOptional[int] = None
    barangay_id: _BLOptional[int] = None


class BLBarangayUpdate(_BLBaseModel):
    name: str


def _bl_iso(dt):
    return dt.isoformat() if dt is not None else None


def _bl_incident_dict(i):
    return {
        'id': i.id, 'barangay_id': i.barangay_id, 'evacuation_center_id': i.evacuation_center_id,
        'disaster_type': i.disaster_type, 'started_at': _bl_iso(i.started_at), 'ended_at': _bl_iso(i.ended_at),
        'started_by': i.started_by, 'ended_by': i.ended_by, 'active': i.ended_at is None,
    }


@app.get('/incidents')
def bl_list_incidents(active: bool = False, db: _BLSession = _BLDepends(get_db),
                      user=_BLDepends(auth.get_current_user)):
    Incident = _bl_model('incidents')
    q = db.query(Incident)
    if user.role != 'city_admin':
        q = q.filter(Incident.barangay_id == user.barangay_id)
    if active:
        q = q.filter(Incident.ended_at.is_(None))
    return [_bl_incident_dict(i) for i in q.order_by(Incident.id.desc()).limit(50).all()]


@app.post('/incidents')
async def bl_start_incident(payload: BLIncidentStart, db: _BLSession = _BLDepends(get_db),
                            user=_BLDepends(auth.get_current_user)):
    Incident = _bl_model('incidents')
    brgy_id = payload.barangay_id if user.role == 'city_admin' else user.barangay_id
    if brgy_id is None:
        raise _BLHTTPException(status_code=422, detail='Choose which barangay is evacuating.')
    if db.query(_bl_model('barangays')).filter_by(id=brgy_id).first() is None:
        raise _BLHTTPException(status_code=404, detail='Barangay not found.')
    kind = (payload.disaster_type or '').strip().capitalize()
    if kind not in BL_DISASTERS:
        raise _BLHTTPException(status_code=422, detail='Disaster type must be one of: ' + ', '.join(BL_DISASTERS) + '.')
    if payload.evacuation_center_id is not None and db.query(_bl_model('evacuation_centers')).filter_by(id=payload.evacuation_center_id).first() is None:
        raise _BLHTTPException(status_code=404, detail='Evacuation center not found.')
    if db.query(Incident).filter(Incident.barangay_id == brgy_id, Incident.ended_at.is_(None)).first():
        raise _BLHTTPException(status_code=409, detail='An evacuation is already active for this barangay. End it before starting a new one.')
    i = Incident(barangay_id=brgy_id, evacuation_center_id=payload.evacuation_center_id, disaster_type=kind,
                 started_at=_BL3dt.utcnow(), started_by=user.id)
    db.add(i)
    db.commit()
    db.refresh(i)
    await _bl_notify(brgy_id)
    return _bl_incident_dict(i)


@app.post('/incidents/{incident_id}/end')
async def bl_end_incident(incident_id: int, db: _BLSession = _BLDepends(get_db),
                          user=_BLDepends(auth.get_current_user)):
    Incident = _bl_model('incidents')
    i = db.query(Incident).filter(Incident.id == incident_id).first()
    if not i:
        raise _BLHTTPException(status_code=404, detail='Evacuation not found.')
    if not _bl_can_edit(user, i.barangay_id):
        raise _BLHTTPException(status_code=403, detail='You can only end your own barangay\'s evacuation.')
    if i.ended_at is not None:
        raise _BLHTTPException(status_code=409, detail='This evacuation has already ended.')
    i.ended_at = _BL3dt.utcnow()
    i.ended_by = user.id
    db.commit()
    db.refresh(i)
    await _bl_notify(i.barangay_id)
    return _bl_incident_dict(i)


@app.put('/barangays/{barangay_id}')
async def bl_update_barangay(barangay_id: int, payload: BLBarangayUpdate, db: _BLSession = _BLDepends(get_db),
                             user=_BLDepends(auth.get_current_user)):
    Barangay = _bl_model('barangays')
    b = db.query(Barangay).filter(Barangay.id == barangay_id).first()
    if not b:
        raise _BLHTTPException(status_code=404, detail='Barangay not found.')
    if not _bl_can_edit(user, barangay_id):
        raise _BLHTTPException(status_code=403, detail='You can only edit your own barangay.')
    name = (payload.name or '').strip()
    if not name:
        raise _BLHTTPException(status_code=422, detail='Barangay name cannot be empty.')
    clash = db.query(Barangay).filter(_BL3func.lower(Barangay.name) == name.lower(), Barangay.id != barangay_id).first()
    if clash:
        raise _BLHTTPException(status_code=409, detail='Another barangay already uses this name.')
    b.name = name
    db.commit()
    await _bl_notify(barangay_id)
    return {'id': b.id, 'name': b.name}


@app.delete('/barangays/{barangay_id}')
async def bl_delete_barangay(barangay_id: int, db: _BLSession = _BLDepends(get_db),
                             user=_BLDepends(auth.get_current_user)):
    if user.role != 'city_admin':
        raise _BLHTTPException(status_code=403, detail='Only the City Admin can delete a barangay.')
    Barangay = _bl_model('barangays')
    b = db.query(Barangay).filter(Barangay.id == barangay_id).first()
    if not b:
        raise _BLHTTPException(status_code=404, detail='Barangay not found.')
    links = [
        ('evacuation centers', _bl_model('evacuation_centers'), 'barangay_id'),
        ('registered evacuees', _bl_model('evacuees'), 'registered_barangay_id'),
        ('user accounts', _bl_model('users'), 'barangay_id'),
        ('households', _bl_model('households'), 'registered_barangay_id'),
        ('evacuation records', _bl_model('incidents'), 'barangay_id'),
    ]
    found = []
    for label, M, col in links:
        n = db.query(M).filter(getattr(M, col) == barangay_id).count()
        if n:
            found.append('%d %s' % (n, label))
    if found:
        raise _BLHTTPException(status_code=409, detail='This barangay still has ' + ', '.join(found) + '. Remove or move them first.')
    db.delete(b)
    db.commit()
    return {'deleted': barangay_id}


# ---- BilisLikas 2.0: pre-registration with webcam photos (batch 4) ----
class BLFaceImages(_BLBaseModel):
    images: list
    angles: _BLOptional[list] = None


class BLMemberCreate(_BLBaseModel):
    full_name: str
    birthdate: _BLDate
    sex: str
    address: str
    contact_number: _BLOptional[str] = None
    civil_status: _BLOptional[str] = None
    special_needs: _BLOptional[list] = None
    emergency_contact: _BLOptional[str] = None


@app.post('/faces/encode')
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
        raise _BLHTTPException(status_code=503, detail='Face recognition is not installed on the server.')
    images = payload.images or []
    if not 1 <= len(images) <= 5:
        raise _BLHTTPException(status_code=422, detail='Send between 1 and 5 photos.')
    angles = payload.angles or []
    photos, encodings = [], []
    for idx, data in enumerate(images):
        label = str(angles[idx]) if idx < len(angles) else 'photo %d' % (idx + 1)
        try:
            raw = data.split(',', 1)[1] if str(data).startswith('data:') else data
            img = Image.open(io.BytesIO(base64.b64decode(raw))).convert('RGB')
        except Exception:
            photos.append({'angle': label, 'ok': False, 'message': 'The ' + label + ' photo could not be read. Retake it.'})
            continue
        arr = np.array(img)
        locs = face_recognition.face_locations(arr, number_of_times_to_upsample=1, model='hog')
        if not locs:
            photos.append({'angle': label, 'ok': False, 'message': 'No face found in the ' + label + ' photo. Face the light, remove caps or sunglasses, and turn the head a little less.'})
            continue
        if len(locs) > 1:
            photos.append({'angle': label, 'ok': False, 'message': 'More than one face in the ' + label + ' photo. Only the evacuee should be in view.'})
            continue
        encodings.append(face_recognition.face_encodings(arr, known_face_locations=locs, num_jitters=1)[0])
        photos.append({'angle': label, 'ok': True, 'message': 'Face found in the ' + label + ' photo.'})
    ok = len(encodings) == len(images)
    worst = 0.0
    if ok and len(encodings) > 1:
        worst = max(float(np.linalg.norm(a - b)) for i, a in enumerate(encodings) for b in encodings[i + 1:])
        if worst > 0.6:
            ok = False
            photos.append({'angle': 'all', 'ok': False, 'message': 'The photos do not look like the same person. Retake all three.'})
    return {
        'ok': ok, 'photos': photos, 'max_distance': round(worst, 3),
        'embedding': [float(x) for x in np.mean(encodings, axis=0)] if ok else None,
    }


@app.post('/households/{household_id}/members')
async def bl_add_member(household_id: int, payload: BLMemberCreate, db: _BLSession = _BLDepends(get_db),
                        user=_BLDepends(auth.get_current_user)):
    Household = _bl_model('households')
    Evacuee = _bl_model('evacuees')
    h = db.query(Household).filter(Household.id == household_id).first()
    if not h:
        raise _BLHTTPException(status_code=404, detail='Household not found.')
    if not _bl_can_edit(user, h.registered_barangay_id):
        raise _BLHTTPException(status_code=403, detail='You can only add members to your own barangay\'s households.')
    if not payload.full_name.strip() or not payload.address.strip() or not payload.sex.strip():
        raise _BLHTTPException(status_code=422, detail='Full name, sex, and address are required.')
    birth = payload.birthdate
    if isinstance(Evacuee.birthdate.property.columns[0].type, _BLString):
        birth = birth.isoformat()
    needs = ','.join(sorted({str(x).strip() for x in (payload.special_needs or []) if str(x).strip()})) or None
    e = Evacuee(full_name=payload.full_name.strip(), birthdate=birth, sex=payload.sex.strip(), address=payload.address.strip(),
                contact_number=(payload.contact_number or '').strip() or None, registered_barangay_id=h.registered_barangay_id,
                household_id=h.id, is_head_of_family=False, identification_method='facial_recognition',
                civil_status=payload.civil_status, special_needs=needs, emergency_contact=payload.emergency_contact)
    db.add(e)
    db.commit()
    db.refresh(e)
    await _bl_notify(h.registered_barangay_id)
    return _bl_evacuee_dict(e)


@app.get('/evacuee_details')
def bl_evacuee_details(db: _BLSession = _BLDepends(get_db), user=_BLDepends(auth.get_current_user)):
    Evacuee = _bl_model('evacuees')
    q = db.query(Evacuee)
    if user.role != 'city_admin':
        q = q.filter(Evacuee.registered_barangay_id == user.barangay_id)
    return [{
        'id': e.id, 'civil_status': e.civil_status, 'emergency_contact': e.emergency_contact,
        'special_needs': [x for x in (e.special_needs or '').split(',') if x],
    } for e in q.all()]
