"""AiVacuwise: quality safeguards based on the ISO/IEC 25010 Software Quality Model.

Installed from main.py with:  import iso_quality; iso_quality.install(app)

Security
  - Deny by default: every API request needs a valid sign-in token, except the public pages
    and sign-in/sign-up endpoints listed in PUBLIC. Role checks inside each endpoint still apply.
  - Device endpoints (/checkin, /gps_pings, POST /trackers) also accept the header X-Device-Key
    when BL_DEVICE_KEY is set in .env, so the Raspberry Pi and trackers can post without a person signing in.
  - Only the City Hall IT Administrator can create accounts through POST /users.
  - Sign-in lockout: 5 failed sign-ins from the same IP address within 15 minutes are blocked for 15 minutes.
  - Browser security headers on every response.
Accountability
  - Activity log: every add, edit and delete (POST/PUT/PATCH/DELETE) is saved with the time, user,
    action, page address, result and IP address.  GET /admin/activity_logs  (IT Administrator only)
Reliability
  - GET /health  checks that the server and database are running.
  - Unexpected errors return a short, friendly message and are written to logs/errors.log.
Performance efficiency
  - Responses larger than 1 KB are compressed (gzip) to load faster on the local network.
"""

import contextvars
import logging
import os
import traceback
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from jose import JWTError, jwt
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    event,
    func,
    insert,
    select,
    text,
)
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session as _OrmSession
from starlette.middleware.gzip import GZipMiddleware

import auth
from database import engine

START = datetime.utcnow()
DEVICE_KEY = (os.getenv("BL_DEVICE_KEY") or "").strip()
LOCK_LIMIT, LOCK_MINUTES = 5, 15

# Paths anyone may open without signing in (exact match or prefix ending with '/').
PUBLIC_EXACT = {
    "/",
    "/login",
    "/register",
    "/register/config",
    "/districts",
    "/admin/register",
    "/admin/register/config",
    "/dashboard",
    "/kiosk",
    "/health",
    "/favicon.ico",
    "/docs",
    "/openapi.json",
    "/relief/items",
}
PUBLIC_PREFIX = ("/static/", "/password/", "/resident/", "/sms/device/", "/sync/", "/ws")
DEVICE_PATHS = {("POST", "/checkin"), ("POST", "/gps_pings"), ("POST", "/trackers")}
NOT_LOGGED = ("/faces/check", "/gps_pings", "/login", "/sms/device/", "/sync/", "/resident/login")

_meta = MetaData()
activity = Table(
    "activity_logs",
    _meta,
    Column("id", Integer, primary_key=True),
    Column("time", DateTime, nullable=False, index=True),
    Column("username", String, nullable=True, index=True),
    Column("method", String, nullable=False),
    Column("path", String, nullable=False),
    Column("status", Integer, nullable=False),
    Column("ip", String, nullable=True),
    Column("details", Text, nullable=True),
)
try:
    _meta.create_all(engine)
    with engine.begin() as _c:
        if _c.dialect.name == "postgresql":  # do not wait forever on a locked table
            _c.execute(text("SET LOCAL lock_timeout = '5s'"))
        _c.execute(text("ALTER TABLE activity_logs ADD COLUMN IF NOT EXISTS details TEXT"))
except Exception as exc:
    print("iso_quality: could not create activity_logs table:", exc)

# ---------- what exactly changed (for the activity log) ----------
_changes = contextvars.ContextVar("bl_changes", default=None)
NOUN = {
    "evacuees": "Evacuee",
    "evacuation_centers": "Evacuation center",
    "barangays": "Barangay",
    "users": "Account",
    "incidents": "Evacuation",
    "relief_records": "Relief record",
    "checkin_records": "Check-in",
    "trackers": "Tracker",
    "households": "Family",
    "transfers": "Transfer",
    "center_change_requests": "Center request",
    "sms_messages": "SMS",
    "gps_pings": "GPS location",
}
HIDE = (
    "password",
    "embedding",
    "token",
    "secret",
    "hash",
    "photo",
    "face",
    "uuid",
    "sync",
    "updated_at",
    "created_at",
    "origin",
    "version",
    "resumed_at",
    "active_seconds",
)
SKIP_TABLES = {
    "activity_logs",
    "login_logs",
    "sync_log",
    "sync_state",
    "sync_tombstones",
    "gps_pings",
    "tracker_pings",
}


def _label(obj):
    for a in ("full_name", "name", "item", "disaster_type", "device_id", "email", "username"):
        v = getattr(obj, a, None)
        if v:
            return str(v)
    return "#" + str(getattr(obj, "id", "") or "new")


def _val(v):
    if v is None or v == "":
        return "blank"
    if hasattr(v, "value"):
        v = v.value
    if hasattr(v, "strftime"):
        v = v.strftime("%b %d, %Y %I:%M %p") if hasattr(v, "hour") else v.strftime("%b %d, %Y")
    v = str(v)
    return '"' + (v[:60] + "..." if len(v) > 60 else v) + '"'


@event.listens_for(_OrmSession, "before_flush")
def _record_changes(session, flush_context, instances):
    out = _changes.get()
    if out is None:
        return
    try:
        for obj in list(session.new):
            t = getattr(obj, "__tablename__", "")
            if t and t not in SKIP_TABLES:
                out.append("Added %s %s" % (NOUN.get(t, t.replace("_", " ")).lower(), _label(obj)))
        for obj in list(session.deleted):
            t = getattr(obj, "__tablename__", "")
            if t and t not in SKIP_TABLES:
                out.append(
                    "Deleted %s %s" % (NOUN.get(t, t.replace("_", " ")).lower(), _label(obj))
                )
        for obj in list(session.dirty):
            t = getattr(obj, "__tablename__", "")
            if not t or t in SKIP_TABLES:
                continue
            parts = []
            for attr in sa_inspect(obj).mapper.column_attrs:
                key = attr.key
                if any(h in key for h in HIDE):
                    continue
                h = sa_inspect(obj).attrs[key].history
                if h.has_changes() and h.deleted and h.added and h.deleted[0] != h.added[0]:
                    parts.append(
                        "%s changed from %s to %s"
                        % (
                            key.replace("_id", "").replace("_", " "),
                            _val(h.deleted[0]),
                            _val(h.added[0]),
                        )
                    )
                elif h.has_changes() and h.added and not h.deleted:
                    parts.append(
                        "%s set to %s"
                        % (key.replace("_id", "").replace("_", " "), _val(h.added[0]))
                    )
            if parts:
                out.append(
                    "%s %s: %s" % (NOUN.get(t, t.replace("_", " ")), _label(obj), ", ".join(parts))
                )
    except Exception as exc:
        err_log.error("activity details failed: %s", exc)


os.makedirs("logs", exist_ok=True)
err_log = logging.getLogger("bilislikas.errors")
if not err_log.handlers:
    h = logging.FileHandler("logs/errors.log")
    h.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    err_log.addHandler(h)
    err_log.setLevel(logging.ERROR)


# Short, easy-to-type addresses: /city -> /static/app/city.html, and / opens the home page
SHORT = {
    "": "index",
    "home": "index",
    "signin": "signin",
    "login": "signin",
    "admin": "admin-signin",
    "cityhall": "admin-signin",
    "register": "register",
    "signup": "register",
    "resident": "resident-signin",
    "city": "city",
    "overview": "city",
    "live": "live",
    "evacuees": "evacuees",
    "preregister": "preregister",
    "centers": "centers",
    "trackers": "trackers",
    "barangays": "barangays",
    "relief": "relief",
    "history": "history",
    "accounts": "accounts",
    "report": "report",
    "entrance": "entrance",
    "display": "display",
    "privacy": "privacy",
    "home-brgy": "dashboard",
}


def _is_public(path):
    return path in PUBLIC_EXACT or path.startswith(PUBLIC_PREFIX)


def _token_user(request):
    h = request.headers.get("authorization", "")
    if not h.lower().startswith("bearer "):
        return None
    try:
        return jwt.decode(h[7:], auth.SECRET_KEY, algorithms=[auth.ALGORITHM]).get("sub")
    except JWTError:
        return None


def _ip(request):
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else None)


def _recent_failures(ip):
    try:
        import login_log

        since = datetime.utcnow() - timedelta(minutes=LOCK_MINUTES)
        with engine.connect() as c:
            return (
                c.execute(
                    select(func.count())
                    .select_from(login_log.logs)
                    .where(
                        login_log.logs.c.ip == ip,
                        login_log.logs.c.result == "failed",
                        login_log.logs.c.time >= since,
                    )
                ).scalar()
                or 0
            )
    except Exception:
        return 0


def _is_it_admin_name(username):
    try:
        import approvals
        import models
        from database import SessionLocal

        db = SessionLocal()
        try:
            u = db.query(models.User).filter(models.User.username == username).first()
            return bool(u and approvals.is_it_admin(u))
        finally:
            db.close()
    except Exception:
        return False


def install(app):
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    @app.middleware("http")
    async def _quality_guard(request: Request, call_next):
        path, method = request.url.path, request.method
        key = path.strip("/").lower()
        if (
            method == "GET" and key in SHORT and "text/html" in request.headers.get("accept", "")
        ):  # browsers only, never API calls
            q = ("?" + request.url.query) if request.url.query else ""
            return RedirectResponse("/static/app/" + SHORT[key] + ".html" + q, status_code=307)
        user = _token_user(request)
        _changes.set([] if method in ("POST", "PUT", "PATCH", "DELETE") else None)

        # Security: sign-in lockout
        if path == "/login" and method == "POST" and _recent_failures(_ip(request)) >= LOCK_LIMIT:
            return JSONResponse(
                {
                    "detail": "Too many failed sign-ins. Please wait %d minutes and try again."
                    % LOCK_MINUTES
                },
                status_code=429,
            )

        # Security: deny by default
        if method != "OPTIONS" and not _is_public(path) and not user:
            device_ok = (method, path) in DEVICE_PATHS and (
                not DEVICE_KEY or request.headers.get("x-device-key", "") == DEVICE_KEY
            )
            if not device_ok:
                return JSONResponse({"detail": "Please sign in first."}, status_code=401)

        # Security: only the IT Administrator creates accounts directly
        if path == "/users" and method == "POST" and not _is_it_admin_name(user):
            return JSONResponse(
                {"detail": "Only the City Hall IT Administrator can create accounts."},
                status_code=403,
            )

        response = await call_next(request)

        # Security headers
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "same-origin")

        # Accountability: activity log of changes
        if method in ("POST", "PUT", "PATCH", "DELETE") and not path.startswith(NOT_LOGGED):
            try:
                with engine.begin() as c:
                    found = _changes.get() or []
                    seen = []
                    for d in found:
                        if d not in seen:
                            seen.append(d)
                    c.execute(
                        insert(activity).values(
                            time=datetime.utcnow(),
                            username=user or "device/anonymous",
                            method=method,
                            path=path[:300],
                            status=response.status_code,
                            ip=_ip(request),
                            details=("; ".join(seen)[:2000] or None),
                        )
                    )
            except Exception as exc:
                err_log.error("activity log failed: %s", exc)
        return response

    # Reliability: friendly error message and error log
    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception):
        err_log.error("%s %s\n%s", request.method, request.url.path, traceback.format_exc())
        return JSONResponse(
            {
                "detail": "Something went wrong on the server. Please try again. If it continues, contact the City Hall IT Administrator."
            },
            status_code=500,
        )

    @app.get("/health")
    def health():
        db_ok = True
        try:
            with engine.connect() as c:
                c.execute(text("SELECT 1"))
        except Exception:
            db_ok = False
        return {
            "status": "ok" if db_ok else "degraded",
            "database": "connected" if db_ok else "not reachable",
            "server_time": datetime.utcnow().isoformat() + "Z",
            "uptime_minutes": int((datetime.utcnow() - START).total_seconds() // 60),
        }

    @app.get("/admin/activity_logs")
    def activity_logs(limit: int = 500, me=Depends(auth.get_current_user)):
        import approvals

        if not approvals.is_it_admin(me):
            raise HTTPException(
                status_code=403,
                detail="Only the City Hall IT Administrator can view the activity log.",
            )
        with engine.connect() as c:
            rows = (
                c.execute(
                    select(activity).order_by(activity.c.id.desc()).limit(max(1, min(limit, 2000)))
                )
                .mappings()
                .all()
            )
        return [
            dict(r, time=r["time"].isoformat() + "Z", action=describe(r["method"], r["path"]))
            for r in rows
        ]


ACTIONS = [
    ("/evacuees/", "/tracker", "Changed the tracker of an evacuee"),
    ("/evacuees/", "/photo", "Uploaded an evacuee photo"),
    ("/evacuees/", "/facial_embedding", "Saved face ID of an evacuee"),
    ("/evacuees", "", "evacuee"),
    ("/evacuation_centers", "", "evacuation center"),
    ("/barangays/", "/info", "Edited barangay details"),
    ("/barangays/", "/district", "Set barangay district"),
    ("/barangays", "", "barangay"),
    ("/incidents/", "/end", "Finished an evacuation"),
    ("/incidents/", "/resume", "Resumed an evacuation"),
    ("/incidents", "", "Started an evacuation"),
    ("/checkin", "", "Recorded a check-in"),
    ("/relief", "", "relief record"),
    ("/households", "", "family"),
    ("/center-requests/", "/approve", "Approved a center request"),
    ("/center-requests/", "/reject", "Rejected a center request"),
    ("/center-requests", "", "Sent a center change request"),
    ("/admin/users/", "", "Changed an account"),
    ("/users", "", "Created an account"),
    ("/register", "", "Requested a barangay account"),
    ("/sms/resend", "", "Sent the SMS alert again"),
    ("/password/", "", "Password reset"),
    ("/transfers", "", "transfer"),
]


def describe(method, path):
    verb = {"POST": "Added", "PUT": "Edited", "PATCH": "Edited", "DELETE": "Deleted"}.get(
        method, method
    )
    for start, end, text_ in ACTIONS:
        if path.startswith(start) and (not end or path.endswith(end)):
            return text_ if text_[0].isupper() else verb + " " + text_
    return verb + " " + path
