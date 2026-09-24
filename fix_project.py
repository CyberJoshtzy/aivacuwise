with open('schemas.py') as f:
    schemas_content = f.read()

old_evacuee_create = '''class EvacueeCreate(BaseModel):
    full_name: str
    birthdate: Optional[datetime] = None
    sex: Optional[str] = None
    address: Optional[str] = None
    contact_number: Optional[str] = None
    facial_embedding: Optional[str] = None
    registered_barangay_id: Optional[int] = None'''

new_evacuee_create = old_evacuee_create + '\n    identification_method: Optional[str] = "manual"'

if 'identification_method' not in schemas_content:
    if old_evacuee_create in schemas_content:
        schemas_content = schemas_content.replace(old_evacuee_create, new_evacuee_create, 1)
        print('schemas.py: identification_method added to EvacueeCreate')
    else:
        print('schemas.py: WARNING could not find EvacueeCreate anchor, skipped')
else:
    print('schemas.py: identification_method already present, skipped')

if 'TransferCreate' not in schemas_content:
    schemas_content += '''

class TransferCreate(BaseModel):
    evacuee_id: int
    from_center_id: Optional[int] = None
    to_center_id: int

class TransferOut(BaseModel):
    id: int
    evacuee_id: int
    from_center_id: Optional[int] = None
    to_center_id: int
    timestamp: datetime
    approved_by: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)

class WalkinCheckinCreate(BaseModel):
    full_name: str
    birthdate: Optional[datetime] = None
    sex: Optional[str] = None
    address: Optional[str] = None
    contact_number: Optional[str] = None
    registered_barangay_id: Optional[int] = None
    evacuation_center_id: int

class WalkinCheckinOut(BaseModel):
    evacuee: EvacueeOut
    checkin: CheckinOut
'''
    print('schemas.py: Transfer and Walkin schemas appended')
else:
    print('schemas.py: Transfer/Walkin schemas already present, skipped')

with open('schemas.py', 'w') as f:
    f.write(schemas_content)


with open('main.py') as f:
    main_content = f.read()

old_imports = '''from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing import List
from database import get_db
import models
import schemas
import auth'''

new_imports = '''from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from datetime import datetime
from database import get_db
import models
import schemas
import auth'''

if 'from datetime import datetime' not in main_content:
    if old_imports in main_content:
        main_content = main_content.replace(old_imports, new_imports, 1)
        print('main.py: datetime and func imports added')
    else:
        print('main.py: WARNING could not find import anchor, skipped')
else:
    print('main.py: datetime import already present, skipped')

old_evacuees_at_center = '''@app.get("/evacuation_centers/{center_id}/evacuees")
def evacuees_at_center(center_id: int, db: Session = Depends(get_db)):
    checkins = (
        db.query(models.CheckinRecord)
        .filter(models.CheckinRecord.evacuation_center_id == center_id)
        .filter(models.CheckinRecord.event_type == "check_in")
        .all()
    )
    evacuee_ids = [c.evacuee_id for c in checkins]
    return db.query(models.Evacuee).filter(models.Evacuee.id.in_(evacuee_ids)).all()'''

new_evacuees_at_center = '''@app.get("/evacuation_centers/{center_id}/evacuees")
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

if 'latest_sub' not in main_content:
    if old_evacuees_at_center in main_content:
        main_content = main_content.replace(old_evacuees_at_center, new_evacuees_at_center, 1)
        print('main.py: evacuees_at_center fixed')
    else:
        print('main.py: WARNING could not find evacuees_at_center anchor, skipped')
else:
    print('main.py: evacuees_at_center fix already present, skipped')

if '/checkin/walkin' not in main_content and 'def create_transfer' not in main_content:
    new_endpoints = '''

@app.post("/transfers", response_model=schemas.TransferOut)
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
'''
    main_content += new_endpoints
    print('main.py: transfer, walk-in, and history endpoints appended')
else:
    print('main.py: new endpoints already present, skipped')

with open('main.py', 'w') as f:
    f.write(main_content)

print('DONE')
