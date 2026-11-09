import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from database import Base


class UserRole(str, enum.Enum):  # noqa: UP042
    barangay_official = "barangay_official"
    city_admin = "city_admin"


class Barangay(Base):
    __tablename__ = "barangays"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)

    centers = relationship("EvacuationCenter", back_populates="barangay")


class EvacuationCenter(Base):
    __tablename__ = "evacuation_centers"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    address = Column(String)
    capacity = Column(Integer, default=0)
    barangay_id = Column(Integer, ForeignKey("barangays.id"))

    barangay = relationship("Barangay", back_populates="centers")


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=True)
    full_name = Column(String, nullable=True)
    designation = Column(String, nullable=True)
    mobile_number = Column(String, nullable=True)
    password_hash = Column(String, nullable=False)
    role = Column(Enum(UserRole), nullable=False)
    barangay_id = Column(Integer, ForeignKey("barangays.id"), nullable=True)
    position = Column(String, nullable=True)
    office = Column(String, nullable=True)
    employee_id = Column(String, nullable=True)
    account_status = Column(String, nullable=True, default="active")
    is_superuser = Column(Boolean, nullable=True, default=False)


class Evacuee(Base):
    __tablename__ = "evacuees"
    id = Column(Integer, primary_key=True)
    full_name = Column(String, nullable=False)
    birthdate = Column(DateTime, nullable=True)
    sex = Column(String, nullable=True)
    address = Column(String, nullable=True)
    contact_number = Column(String, nullable=True)
    facial_embedding = Column(Text, nullable=True)
    registered_barangay_id = Column(Integer, ForeignKey("barangays.id"), nullable=True)
    identification_method = Column(String, nullable=True, default="manual")
    civil_status = Column(String, nullable=True)
    special_needs = Column(String, nullable=True)
    emergency_contact = Column(String, nullable=True)
    household_id = Column(Integer, ForeignKey("households.id"), nullable=True)
    is_head_of_family = Column(Boolean, nullable=True, default=False)


class CheckinRecord(Base):
    __tablename__ = "checkin_records"
    id = Column(Integer, primary_key=True)
    evacuee_id = Column(Integer, ForeignKey("evacuees.id"), nullable=False)
    evacuation_center_id = Column(Integer, ForeignKey("evacuation_centers.id"), nullable=False)
    event_type = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)


class Tracker(Base):
    __tablename__ = "trackers"
    id = Column(Integer, primary_key=True)
    device_id = Column(String, unique=True, nullable=False)
    assigned_evacuee_id = Column(Integer, ForeignKey("evacuees.id"), nullable=True)
    battery_level = Column(Integer, nullable=True)
    tracking_method = Column(String, nullable=True)


class TrackerPing(Base):
    __tablename__ = "tracker_pings"
    id = Column(Integer, primary_key=True)
    tracker_id = Column(Integer, ForeignKey("trackers.id"), nullable=False)
    evacuation_center_id = Column(Integer, ForeignKey("evacuation_centers.id"), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)


class Transfer(Base):
    __tablename__ = "transfers"
    id = Column(Integer, primary_key=True)
    evacuee_id = Column(Integer, ForeignKey("evacuees.id"), nullable=False)
    from_center_id = Column(Integer, ForeignKey("evacuation_centers.id"), nullable=True)
    to_center_id = Column(Integer, ForeignKey("evacuation_centers.id"), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)


class GpsPing(Base):
    __tablename__ = "gps_pings"

    id = Column(Integer, primary_key=True, index=True)
    tracker_id = Column(Integer, ForeignKey("trackers.id"), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    source = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)


class Household(Base):
    __tablename__ = "households"
    id = Column(Integer, primary_key=True)
    registered_barangay_id = Column(Integer, ForeignKey("barangays.id"), nullable=False)
    head_of_family_evacuee_id = Column(Integer, ForeignKey("evacuees.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Incident(Base):
    __tablename__ = "incidents"
    id = Column(Integer, primary_key=True, index=True)
    barangay_id = Column(Integer, ForeignKey("barangays.id"), nullable=False)
    evacuation_center_id = Column(Integer, ForeignKey("evacuation_centers.id"), nullable=True)
    disaster_type = Column(String, nullable=False)
    started_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    started_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    ended_by = Column(Integer, ForeignKey("users.id"), nullable=True)


# ---- Ai-Vacuwise: cloud sync phase 1 (sync-ready records) ----
import os as _sync_os
import uuid as _sync_uuid

from sqlalchemy import event as _sync_event
from sqlalchemy.orm import Session as _SyncSession
from sqlalchemy.orm import object_session as _sync_object_session

SERVER_ID = _sync_os.getenv("BILISLIKAS_SERVER_ID", "local")


class ReliefRecord(Base):
    __tablename__ = "relief_records"
    id = Column(Integer, primary_key=True)
    barangay_id = Column(Integer, ForeignKey("barangays.id"), nullable=False, index=True)
    evacuation_center_id = Column(Integer, ForeignKey("evacuation_centers.id"), nullable=True)
    category = Column(String, nullable=False)
    item = Column(String, nullable=False)
    quantity = Column(Float, nullable=False)
    unit = Column(String, nullable=False)
    recipients = Column(Integer, nullable=True)
    given_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    recorded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    notes = Column(String, nullable=True)


SYNCED_MODELS = [
    Barangay,
    EvacuationCenter,
    User,
    Household,
    Evacuee,
    CheckinRecord,
    Transfer,
    Tracker,
    TrackerPing,
    GpsPing,
    Incident,
    ReliefRecord,
]

for _cls in SYNCED_MODELS:
    _cls.uuid = Column(String(36), unique=True, index=True, nullable=True)
    _cls.updated_at = Column(DateTime, nullable=True, index=True)
    _cls.origin = Column(String, nullable=True)
    _cls.sync_dirty = Column(Boolean, nullable=True, default=False, index=True)

Barangay.district = Column(String, nullable=True)

# Family details (pre-registration update): infant guardian link, typed home barangay, family size
Evacuee.guardian_evacuee_id = Column(Integer, ForeignKey("evacuees.id"), nullable=True)
Evacuee.home_barangay = Column(String, nullable=True)
Household.member_count = Column(Integer, nullable=True)
Incident.finished = Column(Boolean, nullable=True, default=False)
# Active time only: paused periods are not counted in the evacuation duration
Incident.active_seconds = Column(Integer, nullable=True)
Incident.resumed_at = Column(DateTime, nullable=True)


def incident_active_seconds(i, now=None):
    """Seconds the evacuation was actually running (pauses excluded)."""
    now = now or datetime.utcnow()
    base = getattr(i, "active_seconds", None)
    if i.ended_at is not None:
        if base is not None:
            return max(0, int(base))
        return max(0, int((i.ended_at - i.started_at).total_seconds()))  # older records
    since = getattr(i, "resumed_at", None) or i.started_at
    return max(0, int((base or 0) + (now - since).total_seconds()))


class SyncTombstone(Base):
    __tablename__ = "sync_tombstones"
    id = Column(Integer, primary_key=True)
    table_name = Column(String, nullable=False)
    record_uuid = Column(String(36), nullable=False, index=True)
    deleted_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    origin = Column(String, nullable=True)


class SyncState(Base):
    __tablename__ = "sync_state"
    key = Column(String, primary_key=True)
    value = Column(String, nullable=True)


def _sync_importing(target):
    s = _sync_object_session(target)
    return bool(s is not None and s.info.get("sync_import"))


def _sync_on_insert(mapper, connection, target):
    if _sync_importing(target):
        return
    target.sync_dirty = True
    if not getattr(target, "uuid", None):
        target.uuid = str(_sync_uuid.uuid4())
    if not getattr(target, "origin", None):
        target.origin = SERVER_ID
    target.updated_at = datetime.utcnow()


def _sync_on_update(mapper, connection, target):
    if _sync_importing(target):
        return
    target.updated_at = datetime.utcnow()
    target.sync_dirty = True


for _cls in SYNCED_MODELS:
    _sync_event.listen(_cls, "before_insert", _sync_on_insert)
    _sync_event.listen(_cls, "before_update", _sync_on_update)


@_sync_event.listens_for(_SyncSession, "before_flush")
def _sync_record_deletions(session, flush_context, instances):
    if session.info.get("sync_import"):
        return
    for obj in list(session.deleted):
        if type(obj) in SYNCED_MODELS and getattr(obj, "uuid", None):
            session.add(
                SyncTombstone(
                    table_name=obj.__tablename__,
                    record_uuid=obj.uuid,
                    deleted_at=datetime.utcnow(),
                    origin=SERVER_ID,
                )
            )


# ---- Ai-Vacuwise: cloud sync phase 3 (push, pull, notify) ----
class SyncLog(Base):
    """On the cloud hub: every change received, in order, so each server can pull what it has not seen."""

    __tablename__ = "sync_log"
    seq = Column(Integer, primary_key=True)
    table_name = Column(String, nullable=False)
    record_uuid = Column(String(36), nullable=False, index=True)
    is_tombstone = Column(Boolean, nullable=False, default=False)
    origin = Column(String, nullable=False, index=True)
    received_at = Column(DateTime, nullable=False, default=datetime.utcnow)
