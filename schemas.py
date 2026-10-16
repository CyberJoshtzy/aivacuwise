from datetime import datetime

from pydantic import BaseModel, ConfigDict

from models import UserRole


class BarangayCreate(BaseModel):
    name: str


class BarangayOut(BarangayCreate):
    id: int
    district: str | None = None
    model_config = ConfigDict(from_attributes=True)


class EvacuationCenterCreate(BaseModel):
    name: str
    address: str | None = None
    capacity: int | None = 0
    barangay_id: int


class EvacuationCenterOut(EvacuationCenterCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)


class EvacueeCreate(BaseModel):
    full_name: str
    birthdate: datetime | None = None
    sex: str | None = None
    address: str | None = None
    contact_number: str | None = None
    facial_embedding: str | None = None
    registered_barangay_id: int | None = None
    identification_method: str | None = "manual"


class EvacueeOut(EvacueeCreate):
    id: int
    household_id: int | None = None
    is_head_of_family: bool | None = False
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
    email: str | None = None
    password: str
    role: UserRole
    barangay_id: int | None = None


class UserOut(BaseModel):
    id: int
    username: str
    email: str | None = None
    role: UserRole
    barangay_id: int | None = None
    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str


class TrackerCreate(BaseModel):
    device_id: str
    tracking_method: str
    assigned_evacuee_id: int | None = None


class TrackerOut(BaseModel):
    id: int
    device_id: str
    tracking_method: str
    assigned_evacuee_id: int | None = None
    battery_level: int | None = None

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
    from_center_id: int | None = None
    to_center_id: int


class TransferOut(BaseModel):
    id: int
    evacuee_id: int
    from_center_id: int | None = None
    to_center_id: int
    timestamp: datetime
    approved_by: int | None = None

    model_config = ConfigDict(from_attributes=True)


class WalkinCheckinCreate(BaseModel):
    full_name: str
    birthdate: datetime | None = None
    sex: str | None = None
    address: str | None = None
    contact_number: str | None = None
    registered_barangay_id: int | None = None
    evacuation_center_id: int


class WalkinCheckinOut(BaseModel):
    evacuee: EvacueeOut
    checkin: CheckinOut


class HouseholdMemberCreate(BaseModel):
    full_name: str
    birthdate: datetime | None = None
    sex: str | None = None
    address: str | None = None
    contact_number: str | None = None
    is_head_of_family: bool | None = False


class HouseholdCreate(BaseModel):
    registered_barangay_id: int
    members: list[HouseholdMemberCreate]


class HouseholdMemberOut(BaseModel):
    id: int
    full_name: str
    is_head_of_family: bool | None = False
    identification_method: str | None = None

    model_config = ConfigDict(from_attributes=True)


class HouseholdOut(BaseModel):
    id: int
    registered_barangay_id: int
    head_of_family_evacuee_id: int | None = None
    created_at: datetime
    members: list[HouseholdMemberOut] = []

    model_config = ConfigDict(from_attributes=True)


class HouseholdMemberStatus(BaseModel):
    evacuee_id: int
    full_name: str
    is_head_of_family: bool | None = False
    current_center_id: int | None = None
    current_center_name: str | None = None


class HouseholdStatusOut(BaseModel):
    household_id: int
    members: list[HouseholdMemberStatus]


class FacialEmbeddingIn(BaseModel):
    embedding: list[float]


class EnrolledFaceOut(BaseModel):
    evacuee_id: int
    full_name: str
    embedding: list[float]
