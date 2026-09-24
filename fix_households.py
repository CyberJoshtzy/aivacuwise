with open('models.py') as f:
    models_content = f.read()

old_sa_import = 'from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum, Text, Float'
new_sa_import = 'from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum, Text, Float, Boolean'

if 'Boolean' not in models_content.split('\n')[0:5].__str__():
    if old_sa_import in models_content:
        models_content = models_content.replace(old_sa_import, new_sa_import, 1)
        print('models.py: Boolean import added')
    else:
        print('models.py: WARNING sqlalchemy import line not found, skipped')
else:
    print('models.py: Boolean import already present, skipped')

old_evacuee = '''class Evacuee(Base):
    _tablename_ = "evacuees"
    id = Column(Integer, primary_key=True)
    full_name = Column(String, nullable=False)
    birthdate = Column(DateTime, nullable=True)
    sex = Column(String, nullable=True)
    address = Column(String, nullable=True)
    contact_number = Column(String, nullable=True)
    facial_embedding = Column(Text, nullable=True)
    registered_barangay_id = Column(Integer, ForeignKey("barangays.id"), nullable=True)
    identification_method = Column(String, nullable=True, default="manual")'''

new_evacuee = '''class Evacuee(Base):
    _tablename_ = "evacuees"
    id = Column(Integer, primary_key=True)
    full_name = Column(String, nullable=False)
    birthdate = Column(DateTime, nullable=True)
    sex = Column(String, nullable=True)
    address = Column(String, nullable=True)
    contact_number = Column(String, nullable=True)
    facial_embedding = Column(Text, nullable=True)
    registered_barangay_id = Column(Integer, ForeignKey("barangays.id"), nullable=True)
    identification_method = Column(String, nullable=True, default="manual")
    household_id = Column(Integer, ForeignKey("households.id"), nullable=True)
    is_head_of_family = Column(Boolean, nullable=True, default=False)


class Household(Base):
    _tablename_ = "households"
    id = Column(Integer, primary_key=True)
    registered_barangay_id = Column(Integer, ForeignKey("barangays.id"), nullable=False)
    head_of_family_evacuee_id = Column(Integer, ForeignKey("evacuees.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)'''

if 'class Household(Base)' not in models_content:
    if old_evacuee in models_content:
        models_content = models_content.replace(old_evacuee, new_evacuee, 1)
        print('models.py: household_id/is_head_of_family added to Evacuee, Household class added')
    else:
        print('models.py: WARNING Evacuee class anchor not found, skipped')
else:
    print('models.py: Household class already present, skipped')

with open('models.py', 'w') as f:
    f.write(models_content)


with open('schemas.py') as f:
    schemas_content = f.read()

old_typing_import = 'from typing import Optional'
new_typing_import = 'from typing import Optional, List'

if 'from typing import Optional, List' not in schemas_content:
    if old_typing_import in schemas_content:
        schemas_content = schemas_content.replace(old_typing_import, new_typing_import, 1)
        print('schemas.py: List import added')
    else:
        print('schemas.py: WARNING typing import line not found, skipped')
else:
    print('schemas.py: List import already present, skipped')

if 'HouseholdCreate' not in schemas_content:
    schemas_content += '''

class HouseholdMemberCreate(BaseModel):
    full_name: str
    birthdate: Optional[datetime] = None
    sex: Optional[str] = None
    address: Optional[str] = None
    contact_number: Optional[str] = None
    is_head_of_family: Optional[bool] = False

class HouseholdCreate(BaseModel):
    registered_barangay_id: int
    members: List[HouseholdMemberCreate]

class HouseholdMemberOut(BaseModel):
    id: int
    full_name: str
    is_head_of_family: Optional[bool] = False
    identification_method: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class HouseholdOut(BaseModel):
    id: int
    registered_barangay_id: int
    head_of_family_evacuee_id: Optional[int] = None
    created_at: datetime
    members: List[HouseholdMemberOut] = []

    model_config = ConfigDict(from_attributes=True)

class HouseholdMemberStatus(BaseModel):
    evacuee_id: int
    full_name: str
    is_head_of_family: Optional[bool] = False
    current_center_id: Optional[int] = None
    current_center_name: Optional[str] = None

class HouseholdStatusOut(BaseModel):
    household_id: int
    members: List[HouseholdMemberStatus]
'''
    print('schemas.py: household schemas appended')
else:
    print('schemas.py: household schemas already present, skipped')

with open('schemas.py', 'w') as f:
    f.write(schemas_content)


with open('main.py') as f:
    main_content = f.read()

if 'def create_household' not in main_content:
    main_content += '''

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
'''
    print('main.py: household endpoints appended')
else:
    print('main.py: household endpoints already present, skipped')

with open('main.py', 'w') as f:
    f.write(main_content)

print('DONE')
