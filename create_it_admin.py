"""Creates (or resets) the City Hall IT Administrator account.

Run on the laptop server:   cd ~/aivacuwise && venv/bin/python create_it_admin.py
The password is printed only in the terminal. Write it down and do not paste it in chats or screenshots.
"""

import secrets
import string

import admin_auth  # noqa: F401  (makes sure the account columns exist)
import auth
import models
from database import SessionLocal

EMAIL = "itadmin@bilislikas.local"

alphabet = string.ascii_letters + string.digits
password = "IT-" + "".join(secrets.choice(alphabet) for _ in range(10)) + str(secrets.randbelow(10))

db = SessionLocal()
u = (
    db.query(models.User)
    .filter((models.User.email == EMAIL) | (models.User.username == EMAIL))
    .first()
)
if u is None:
    u = models.User(username=EMAIL, email=EMAIL, role="city_admin")
    db.add(u)
u.password_hash = auth.get_password_hash(password)
u.full_name = "City Hall IT Administrator"
u.designation = "Management Information Systems Administrator (MIS Administrator)"
u.position = "mis_admin"
u.office = "mis"
u.employee_id = u.employee_id or "MIS-0001"
u.account_status = "active"
u.is_superuser = True
db.commit()
db.close()

print("City Hall IT Administrator account is ready.")
print("  Email:   ", EMAIL)
print("  Password:", password)
print(
    "Sign in at the City Hall Administrator sign-in page. Running this again creates a new password."
)
