from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime
from models import UserRole

class BarangayCreate(BaseModel):
    name: str

class BarangayOut(BarangayCreate):
    id: int
    district: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class EvacuationCenterCreate(BaseModel):
    name: str
    address: Optional[str] = None
    capacity: Optional[int] = 0
    barangay_id: int

class EvacuationCenterOut(EvacuationCenterCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)

class EvacueeCreate(BaseModel):
    full_name: str
    birthdate: Optional[datetime] = None
    sex: Optional[str] = None
    address: Optional[str] = None
    contact_number: Optional[str] = None
    facial_embedding: Optional[str] = None
    registered_barangay_id: Optional[int] = None
    identification_method: Optional[str] = "manual"

class EvacueeOut(EvacueeCreate):
    id: int
    household_id: Optional[int] = None
    is_head_of_family: Optional[bool] = False
    model_config = ConfigDict(from_attributes=True)

class CheckinCreate(BaseModel):
    evacuee_id: int
    evacuation_center_id: int
    event_type: str

class CheckinOut(CheckinCreate):
    id: int
    timestamp: datetime
    model_config = ConfigDict(from_attributes=True)

class UserCreate(BaseModel):
    username: str
    email: Optional[str] = None
    password: str
    role: UserRole
    barangay_id: Optional[int] = None

class UserOut(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    role: UserRole
    barangay_id: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    token_type: str

class TrackerCreate(BaseModel):
    device_id: str
    tracking_method: str
    assigned_evacuee_id: Optional[int] = None

class TrackerOut(BaseModel):
    id: int
    device_id: str
    tracking_method: str
    assigned_evacuee_id: Optional[int] = None
    battery_level: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)

class GpsPingCreate(BaseModel):
    tracker_id: int
    latitude: float
    longitude: float
    source: str

class GpsPingOut(BaseModel):
    id: int
    tracker_id: int
    latitude: float
    longitude: float
    source: str
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)

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


class FacialEmbeddingIn(BaseModel):
    embedding: List[float]


class EnrolledFaceOut(BaseModel):
    evacuee_id: int
    full_name: str
    embedding: List[float]
