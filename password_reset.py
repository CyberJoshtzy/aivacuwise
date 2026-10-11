"""BilisLikas 2.0: forgot password with a 6-digit code sent by email.

Flow:
  1. POST /password/forgot  {email}                       -> where the code can be sent (masked)
  2. POST /password/send    {email}                       -> emails a 6-digit code (valid 10 minutes)
  3. POST /password/verify  {email, code}                 -> checks the code
  4. POST /password/reset   {email, code, new_password}   -> sets the new password

Settings (in .env):
  SMTP_USER, SMTP_PASSWORD     Gmail address and its 16-letter App Password
  SMTP_HOST, SMTP_PORT         optional, default smtp.gmail.com and 465
"""
import hashlib
import hmac
import os
import re
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta
from email.message import EmailMessage

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Session

import auth
import models
from database import Base, get_db

CODE_MINUTES = 10
MAX_ATTEMPTS = 5
RESEND_SECONDS = 60

router = APIRouter()


class PasswordResetCode(Base):
    """Local only, never synced to the cloud. Stores a hash of the code, not the code itself."""
    __tablename__ = "password_reset_codes"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    code_hash = Column(String(64), nullable=False)
    channel = Column(String(10), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    used_at = Column(DateTime, nullable=True)


try:  # create the table on the real database if it does not exist yet
    from database import engine as _engine
    PasswordResetCode.__table__.create(bind=_engine, checkfirst=True)
except Exception:
    pass


class ForgotIn(BaseModel):
    email: str


class SendIn(BaseModel):
    email: str
    channel: str = "email"


class VerifyIn(BaseModel):
    email: str
    code: str


class ResetIn(BaseModel):
    email: str
    code: str
    new_password: str


# ---------- helpers ----------
def _hash(code):
    key = (os.getenv("JWT_SECRET_KEY") or "bilislikas").encode()
    return hmac.new(key, code.encode(), hashlib.sha256).hexdigest()


def _find_user(db, email):
    e = (email or "").strip().lower()
    if not e:
        return None
    return db.query(models.User).filter(func.lower(models.User.email) == e).first()


def mask_email(email):
    name, _, domain = (email or "").partition("@")
    if not domain:
        return ""
    shown = name[:2] if len(name) > 2 else name[:1]
    return shown + "***@" + domain


def _options(user):
    opts = []
    if user.email:
        opts.append({"channel": "email", "label": "Email", "hint": mask_email(user.email)})
    return opts


def _message(code):
    return ("Your BilisLikas 2.0 password reset code is %s. It expires in %d minutes. "
            "If you did not ask for this, ignore this message." % (code, CODE_MINUTES))


def send_email(to_address, code):
    user = (os.getenv("SMTP_USER") or "").strip()
    pw = (os.getenv("SMTP_PASSWORD") or "").replace(" ", "").strip()
    if not user or not pw:
        raise HTTPException(status_code=503, detail="Email sending is not set up on this server yet. Contact your City Admin.")
    msg = EmailMessage()
    msg["Subject"] = "BilisLikas 2.0 password reset code"
    msg["From"] = "BilisLikas 2.0 <%s>" % user
    msg["To"] = to_address
    msg.set_content(_message(code))
    host = os.getenv("SMTP_HOST") or "smtp.gmail.com"
    port = int(os.getenv("SMTP_PORT") or 465)
    try:
        with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=20) as s:
            s.login(user, pw)
            s.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        raise HTTPException(status_code=502, detail="The server's email login was rejected. Check SMTP_USER and SMTP_PASSWORD (App Password).")
    except Exception:
        raise HTTPException(status_code=502, detail="The email could not be sent. Check the server's internet connection and try again.")


def _active_code(db, user):
    return (db.query(PasswordResetCode)
            .filter(PasswordResetCode.user_id == user.id, PasswordResetCode.used_at.is_(None))
            .order_by(PasswordResetCode.id.desc()).first())


def _check_code(db, email, code):
    user = _find_user(db, email)
    code = re.sub(r"\D", "", code or "")
    bad = HTTPException(status_code=400, detail="The code is not correct.")
    if user is None or len(code) != 6:
        raise bad
    row = _active_code(db, user)
    if row is None or row.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="The code has expired. Request a new one.")
    if row.attempts >= MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many wrong tries. Request a new code.")
    if not hmac.compare_digest(row.code_hash, _hash(code)):
        row.attempts += 1
        db.commit()
        left = MAX_ATTEMPTS - row.attempts
        raise HTTPException(status_code=400, detail="The code is not correct. %d tries left." % left if left else "Too many wrong tries. Request a new code.")
    return user, row


# ---------- endpoints ----------
@router.post("/password/forgot")
def forgot(payload: ForgotIn, db: Session = Depends(get_db)):
    user = _find_user(db, payload.email)
    if user is None:
        raise HTTPException(status_code=404, detail="No account uses this email address.")
    opts = _options(user)
    if not opts:
        raise HTTPException(status_code=409, detail="This account has no email address saved. Contact your City Admin.")
    return {"options": opts}


@router.post("/password/send")
def send(payload: SendIn, db: Session = Depends(get_db)):
    user = _find_user(db, payload.email)
    if user is None:
        raise HTTPException(status_code=404, detail="No account uses this email address.")
    channel = (payload.channel or "").strip().lower()
    if channel not in [o["channel"] for o in _options(user)]:
        raise HTTPException(status_code=422, detail="Codes can only be sent by email.")
    last = _active_code(db, user)
    now = datetime.utcnow()
    if last is not None and (now - last.created_at).total_seconds() < RESEND_SECONDS:
        wait = RESEND_SECONDS - int((now - last.created_at).total_seconds())
        raise HTTPException(status_code=429, detail="Please wait %d seconds before requesting another code." % wait)
    code = "%06d" % secrets.randbelow(1000000)
    send_email(user.email, code)
    hint = mask_email(user.email)
    db.query(PasswordResetCode).filter(PasswordResetCode.user_id == user.id,
                                       PasswordResetCode.used_at.is_(None)).update({PasswordResetCode.used_at: now})
    db.add(PasswordResetCode(user_id=user.id, code_hash=_hash(code), channel=channel, created_at=now,
                             expires_at=now + timedelta(minutes=CODE_MINUTES)))
    db.commit()
    return {"sent": True, "channel": channel, "hint": hint, "expires_in_minutes": CODE_MINUTES}


@router.post("/password/verify")
def verify(payload: VerifyIn, db: Session = Depends(get_db)):
    _check_code(db, payload.email, payload.code)
    return {"valid": True}


@router.post("/password/reset")
def reset(payload: ResetIn, db: Session = Depends(get_db)):
    pw = payload.new_password or ""
    if len(pw) < 8 or not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        raise HTTPException(status_code=422, detail="Use a password with at least 8 characters, including letters and a number.")
    user, row = _check_code(db, payload.email, payload.code)
    user.password_hash = auth.get_password_hash(pw)
    row.used_at = datetime.utcnow()
    db.commit()
    return {"reset": True, "email": user.email}
