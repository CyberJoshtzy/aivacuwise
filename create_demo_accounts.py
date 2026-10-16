"""Creates demo accounts for testing and the thesis defense.
City Hall:  admin@bilislikas.local / BilisAdmin2026  (System Administrator, active)
Resident:   Last name Demo, birthday January 15 1990, mobile 09170000001
            (with two family members so the family section has data)
Safe to run again: existing demo records are updated, not duplicated."""
from datetime import datetime
import auth
import models
from database import SessionLocal

db = SessionLocal()
U, E = models.User, models.Evacuee

email = "admin@bilislikas.local"
u = db.query(U).filter(U.email == email).first()
if not u:
    u = U(username=email, email=email, role="city_admin")
    db.add(u)
u.password_hash = auth.get_password_hash("BilisAdmin2026")
u.full_name = "Demo City Administrator"
u.designation = "Management Information Systems Administrator (MIS Administrator)"
u.position, u.office, u.employee_id = "mis_admin", "mis", "DEMO-0001"
u.account_status, u.is_superuser = "active", True
u.mobile_number = "09170000000"
db.commit()
print("City Hall account ready:", email, "/ BilisAdmin2026")

b = db.query(models.Barangay).order_by(models.Barangay.id).first()
if not b:
    print("No barangay found. Register a barangay first, then run this again."); raise SystemExit(1)
head = db.query(E).filter(E.full_name == "Juan Demo").first()
if not head:
    h = models.Household(registered_barangay_id=b.id)
    db.add(h); db.flush()
    head = E(full_name="Juan Demo", birthdate=datetime(1990, 1, 15), sex="Male", civil_status="Married",
             address="123 Sample St., Manila", contact_number="09170000001", registered_barangay_id=b.id,
             household_id=h.id, is_head_of_family=True)
    wife = E(full_name="Maria Demo", birthdate=datetime(1992, 6, 20), sex="Female", civil_status="Married",
             address="123 Sample St., Manila", contact_number="09170000002", registered_barangay_id=b.id,
             household_id=h.id, special_needs="Pregnant")
    kid = E(full_name="Ana Demo", birthdate=datetime(2018, 3, 5), sex="Female", address="123 Sample St., Manila",
            registered_barangay_id=b.id, household_id=h.id)
    db.add_all([head, wife, kid]); db.flush()
    h.head_of_family_evacuee_id = head.id
    if hasattr(h, "member_count"):
        h.member_count = 3
    db.commit()
print("Resident ready in Barangay", b.name + ": last name Demo, birthday January 15 1990, mobile 09170000001")
db.close()
