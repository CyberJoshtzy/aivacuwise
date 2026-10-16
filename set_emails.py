"""Gives the two test accounts an email address. Run after patch_email_login.py."""

import models
from database import get_db

db = next(get_db())
for uname, mail in [
    ("cityadmin", "cityadmin@bilislikas.local"),
    ("brgytest", "brgytest@bilislikas.local"),
]:
    u = db.query(models.User).filter(models.User.username == uname).first()
    if u:
        u.email = mail
        print("set", uname, "->", mail)
    else:
        print("not found:", uname)
db.commit()
