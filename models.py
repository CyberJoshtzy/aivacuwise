from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum, Text, Float, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from database import Base

class UserRole(str, enum.Enum):
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
    password_hash = Column(String, nullable=False)
    role = Column(Enum(UserRole), nullable=False)
    barangay_id = Column(Integer, ForeignKey("barangays.id"), nullable=True)


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
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)\

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
