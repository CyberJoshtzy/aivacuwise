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
    db_user = models.User(username=user.username, password_hash=hashed_password, role=user.role, barangay_id=user.barangay_id)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@app.post("/admin/users", response_model=schemas.UserOut)
def admin_create_user(user: schemas.UserCreate, current_user: models.User = Depends(auth.require_role("city_admin")), db: Session = Depends(get_db)):
    hashed_password = auth.get_password_hash(user.password)
    db_user = models.User(username=user.username, password_hash=hashed_password, role=user.role, barangay_id=user.barangay_id)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@app.post("/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
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
