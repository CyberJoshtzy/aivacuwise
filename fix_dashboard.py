with open('auth.py') as f:
    auth_content = f.read()

if 'get_current_user_from_token' not in auth_content:
    auth_content += '''

def get_current_user_from_token(token: str, db: Session):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            return None
    except JWTError:
        return None
    return db.query(models.User).filter(models.User.username == username).first()
'''
    print('auth.py: get_current_user_from_token added')
else:
    print('auth.py: get_current_user_from_token already present, skipped')

with open('auth.py', 'w') as f:
    f.write(auth_content)


with open('main.py') as f:
    main_content = f.read()

old_imports = '''from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from datetime import datetime
from database import get_db
import models
import schemas
import auth'''

new_imports = '''from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from datetime import datetime
from database import get_db
import models
import schemas
import auth
from connection_manager import manager'''

if 'from connection_manager import manager' not in main_content:
    if old_imports in main_content:
        main_content = main_content.replace(old_imports, new_imports, 1)
        print('main.py: websocket imports added')
    else:
        print('main.py: WARNING import anchor not found, skipped')
else:
    print('main.py: websocket imports already present, skipped')

old_evacuees_at_center = '''@app.get("/evacuation_centers/{center_id}/evacuees")
def evacuees_at_center(center_id: int, db: Session = Depends(get_db)):
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
    return db.query(models.Evacuee).filter(models.Evacuee.id.in_(evacuee_ids)).all()'''

new_evacuees_at_center = '''def _get_current_evacuees_at_center(db: Session, center_id: int):
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
    return _get_current_evacuees_at_center(db, center_id)'''

if '_get_current_evacuees_at_center' not in main_content:
    if old_evacuees_at_center in main_content:
        main_content = main_content.replace(old_evacuees_at_center, new_evacuees_at_center, 1)
        print('main.py: evacuees_at_center refactored into a reusable helper')
    else:
        print('main.py: WARNING evacuees_at_center anchor not found, skipped')
else:
    print('main.py: evacuees_at_center already refactored, skipped')

old_checkin = '''@app.post("/checkin", response_model=schemas.CheckinOut)
def checkin_evacuee(record: schemas.CheckinCreate, db: Session = Depends(get_db)):
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
    return db_record'''

new_checkin = '''@app.post("/checkin", response_model=schemas.CheckinOut)
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
    return db_record'''

if old_checkin in main_content:
    main_content = main_content.replace(old_checkin, new_checkin, 1)
    print('main.py: /checkin now broadcasts updates')
elif 'await manager.broadcast' in main_content and 'async def checkin_evacuee' in main_content:
    print('main.py: /checkin already broadcasts, skipped')
else:
    print('main.py: WARNING /checkin anchor not found, skipped')

old_transfer = '''@app.post("/transfers", response_model=schemas.TransferOut)
def create_transfer(
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
    return db_transfer'''

new_transfer = '''@app.post("/transfers", response_model=schemas.TransferOut)
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

    return db_transfer'''

if old_transfer in main_content:
    main_content = main_content.replace(old_transfer, new_transfer, 1)
    print('main.py: /transfers now broadcasts updates')
elif 'async def create_transfer' in main_content:
    print('main.py: /transfers already broadcasts, skipped')
else:
    print('main.py: WARNING /transfers anchor not found, skipped')

old_walkin = '''@app.post("/checkin/walkin", response_model=schemas.WalkinCheckinOut)
def walkin_register_and_checkin(
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

    return {"evacuee": new_evacuee, "checkin": new_checkin}'''

new_walkin = '''@app.post("/checkin/walkin", response_model=schemas.WalkinCheckinOut)
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

    return {"evacuee": new_evacuee, "checkin": new_checkin}'''

if old_walkin in main_content:
    main_content = main_content.replace(old_walkin, new_walkin, 1)
    print('main.py: /checkin/walkin now broadcasts updates')
elif 'async def walkin_register_and_checkin' in main_content:
    print('main.py: /checkin/walkin already broadcasts, skipped')
else:
    print('main.py: WARNING /checkin/walkin anchor not found, skipped')

old_gps = '''@app.post("/gps_pings", response_model=schemas.GpsPingOut)
def create_gps_ping(ping: schemas.GpsPingCreate, db: Session = Depends(get_db)):
    tracker = db.query(models.Tracker).filter(models.Tracker.id == ping.tracker_id).first()
    if not tracker:
        raise HTTPException(status_code=404, detail="Tracker not found")
    new_ping = models.GpsPing(**ping.model_dump())
    db.add(new_ping)
    db.commit()
    db.refresh(new_ping)
    return new_ping'''

new_gps = '''@app.post("/gps_pings", response_model=schemas.GpsPingOut)
async def create_gps_ping(ping: schemas.GpsPingCreate, db: Session = Depends(get_db)):
    tracker = db.query(models.Tracker).filter(models.Tracker.id == ping.tracker_id).first()
    if not tracker:
        raise HTTPException(status_code=404, detail="Tracker not found")
    new_ping = models.GpsPing(**ping.model_dump())
    db.add(new_ping)
    db.commit()
    db.refresh(new_ping)
    await manager.broadcast({"type": "gps_update", "barangay_id": None, "tracker_id": tracker.id})
    return new_ping'''

if old_gps in main_content:
    main_content = main_content.replace(old_gps, new_gps, 1)
    print('main.py: /gps_pings now broadcasts updates')
elif 'async def create_gps_ping' in main_content:
    print('main.py: /gps_pings already broadcasts, skipped')
else:
    print('main.py: WARNING /gps_pings anchor not found, skipped')

if 'dashboard_summary' not in main_content:
    main_content += '''

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
'''
    print('main.py: /dashboard/summary and /ws/dashboard appended')
else:
    print('main.py: dashboard endpoints already present, skipped')

with open('main.py', 'w') as f:
    f.write(main_content)

print('DONE')
