"""BilisLikas 2.0: GSM SMS Alert Sender.

The laptop server keeps a queue of text messages. An ESP32 with a GSM module (A7670 / SIM7600 / SIM800L)
asks the server for the next message over the local Wi-Fi, sends it as a normal SMS through its SIM card,
and reports back. Works without internet; only cellular signal is needed.

Messages are queued automatically when:
  - an evacuation starts      -> every registered resident of that barangay with a mobile number
  - a resident checks in      -> the head of the family (or the resident) gets a confirmation
  - an evacuation is finished -> "safe to return" notice to the barangay's residents

Endpoints
  ESP32 (header X-SMS-Key: <SMS_DEVICE_KEY from .env>)
    GET  /sms/device/next            next queued message, or 204 if none
    POST /sms/device/{id}/result     {"ok": true} or {"ok": false, "error": "..."}
  Dashboard (signed-in users)
    GET  /sms/log                    recent messages (official: own barangay; City Admin: all)
    POST /sms/test                   {"phone": "0917..."} queue a test message
    GET  /sms/status                 queue counts and when the ESP32 last checked in

.env settings
  SMS_ENABLED=1                      only the barangay laptop server should send (leave unset on the cloud hub)
  SMS_DEVICE_KEY=<long random text>  same value is typed into the ESP32 code
"""
import os
import re
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Integer, String, event
from sqlalchemy.orm import Session

import auth
import models
from database import Base, SessionLocal, get_db

router = APIRouter()
ENABLED = (os.getenv('SMS_ENABLED') or '').strip() in ('1', 'true', 'yes')
_last_seen = {'at': None}


class SmsMessage(Base):
    __tablename__ = 'sms_messages'
    id = Column(Integer, primary_key=True)
    phone = Column(String, nullable=False)
    body = Column(String, nullable=False)
    kind = Column(String, nullable=False, default='manual')   # evacuation_start, checkin, evacuation_end, test
    barangay_id = Column(Integer, nullable=True, index=True)
    status = Column(String, nullable=False, default='queued', index=True)  # queued, sending, sent, failed
    attempts = Column(Integer, nullable=False, default=0)
    error = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    sent_at = Column(DateTime, nullable=True)


try:
    from database import engine as _engine
    SmsMessage.__table__.create(_engine, checkfirst=True)
except Exception as exc:
    print('sms: could not create sms_messages table:', exc)


# ---------- helpers ----------
def normalize(num: Optional[str]) -> Optional[str]:
    """0917 123 4567 / 63917... / +63917... -> +639171234567. Returns None if not a PH mobile number."""
    d = re.sub(r'\D', '', num or '')
    if d.startswith('63') and len(d) == 12:
        d = '0' + d[2:]
    if len(d) == 10 and d.startswith('9'):
        d = '0' + d
    return '+63' + d[1:] if len(d) == 11 and d.startswith('09') else None


def _first(name):
    return (name or '').strip().split(' ')[0] or 'Ka-barangay'


def _local(dt):
    return (dt + timedelta(hours=8)).strftime('%I:%M %p').lstrip('0')  # stored in UTC, shown in PH time


def _queue(db, phone, body, kind, barangay_id=None):
    p = normalize(phone)
    if not p:
        return False
    db.add(SmsMessage(phone=p, body=body[:300], kind=kind, barangay_id=barangay_id))
    return True


# ---------- automatic messages (listen for new incidents and check-ins) ----------
@event.listens_for(Session, 'after_flush')
def _collect(session, ctx):
    if not ENABLED:
        return
    jobs = session.info.setdefault('sms_jobs', [])
    for obj in session.new:
        t = getattr(obj, '__tablename__', '')
        if t == 'incidents':
            jobs.append(('start', obj.id))
        elif t == 'checkin_records' and obj.event_type == 'check_in':
            jobs.append(('checkin', obj.id))
    for obj in session.dirty:
        if getattr(obj, '__tablename__', '') == 'incidents' and obj.ended_at is not None and getattr(obj, 'finished', False):
            if ('end', obj.id) not in jobs:
                jobs.append(('end', obj.id))


@event.listens_for(Session, 'after_commit')
def _send_jobs(session):
    jobs = session.info.pop('sms_jobs', None)
    if not jobs:
        return
    db = SessionLocal()
    try:
        for kind, oid in jobs:
            try:
                _build(db, kind, oid)
            except Exception as exc:
                print('sms: could not queue', kind, oid, exc)
        db.commit()
    finally:
        db.close()


@event.listens_for(Session, 'after_rollback')
def _drop_jobs(session):
    session.info.pop('sms_jobs', None)


def _residents(db, brgy_id):
    return db.query(models.Evacuee).filter(models.Evacuee.registered_barangay_id == brgy_id).all()


def _build(db, kind, oid):
    Incident = models.Incident
    if kind in ('start', 'end'):
        i = db.get(Incident, oid)
        if not i:
            return
        brgy = db.get(models.Barangay, i.barangay_id)
        center = db.get(models.EvacuationCenter, i.evacuation_center_id) if i.evacuation_center_id else None
        where = center.name if center else 'pinakamalapit na evacuation center'
        seen = set()
        for e in _residents(db, i.barangay_id):
            p = normalize(e.contact_number)
            if not p or p in seen:
                continue
            seen.add(p)
            if kind == 'start':
                body = ('BilisLikas 2.0 - {b}: May {d} evacuation. Lumikas na po sa {w}. '
                        'Dalhin ang ID, gamot, tubig at GPS tracker. Humarap sa camera pagpasok.').format(
                    b=brgy.name if brgy else 'Barangay', d=i.disaster_type, w=where)
            else:
                body = ('BilisLikas 2.0 - {b}: Tapos na po ang evacuation. Ligtas nang umuwi. '
                        'Mag-ingat po sa pag-uwi.').format(b=brgy.name if brgy else 'Barangay')
            _queue(db, p, body, 'evacuation_' + kind, i.barangay_id)
    elif kind == 'checkin':
        c = db.get(models.CheckinRecord, oid)
        if not c:
            return
        e = db.get(models.Evacuee, c.evacuee_id)
        center = db.get(models.EvacuationCenter, c.evacuation_center_id)
        if not e:
            return
        to = e.contact_number
        if e.household_id:
            h = db.get(models.Household, e.household_id)
            head = db.get(models.Evacuee, h.head_of_family_evacuee_id) if h and h.head_of_family_evacuee_id else None
            if head and normalize(head.contact_number):
                to = head.contact_number
        body = 'BilisLikas 2.0: Si {n} ay nakarating na sa {c}, {t}. Ligtas po siya.'.format(
            n=e.full_name, c=center.name if center else 'evacuation center', t=_local(c.timestamp or datetime.utcnow()))
        _queue(db, to, body, 'checkin', e.registered_barangay_id)


# ---------- ESP32 endpoints ----------
def _device(key: Optional[str]):
    expected = (os.getenv('SMS_DEVICE_KEY') or '').strip()
    if not expected:
        raise HTTPException(status_code=503, detail='SMS_DEVICE_KEY is not set on this server.')
    if (key or '').strip() != expected:
        raise HTTPException(status_code=401, detail='Wrong SMS device key.')
    _last_seen['at'] = datetime.utcnow()


@router.get('/sms/device/next')
def device_next(x_sms_key: Optional[str] = Header(None), db: Session = Depends(get_db)):
    _device(x_sms_key)
    # a message stuck in "sending" for 2 minutes (ESP32 restarted) goes back to the queue
    stale = datetime.utcnow() - timedelta(minutes=2)
    db.query(SmsMessage).filter(SmsMessage.status == 'sending', SmsMessage.sent_at < stale).update({'status': 'queued'})
    m = (db.query(SmsMessage).filter(SmsMessage.status == 'queued')
         .order_by(SmsMessage.kind.notin_(['evacuation_start', 'evacuation_resend']), SmsMessage.id).first())  # evacuation alerts first
    if not m:
        db.commit()
        return Response(status_code=204)
    m.status, m.attempts, m.sent_at = 'sending', m.attempts + 1, datetime.utcnow()
    db.commit()
    return {'id': m.id, 'phone': m.phone, 'body': m.body}


class Result(BaseModel):
    ok: bool
    error: Optional[str] = None


@router.post('/sms/device/{mid}/result')
def device_result(mid: int, r: Result, x_sms_key: Optional[str] = Header(None), db: Session = Depends(get_db)):
    _device(x_sms_key)
    m = db.get(SmsMessage, mid)
    if not m:
        raise HTTPException(status_code=404, detail='Message not found.')
    if r.ok:
        m.status, m.sent_at, m.error = 'sent', datetime.utcnow(), None
    else:
        m.error = (r.error or 'send failed')[:200]
        m.status = 'queued' if m.attempts < 3 else 'failed'  # retry up to 3 times
    db.commit()
    return {'id': m.id, 'status': m.status}


# ---------- dashboard endpoints ----------
def _is_city(u):
    return (u.role.value if hasattr(u.role, 'value') else u.role) == 'city_admin'


@router.get('/sms/log')
def sms_log(limit: int = 100, user=Depends(auth.get_current_user), db: Session = Depends(get_db)):
    q = db.query(SmsMessage)
    if not _is_city(user):
        q = q.filter(SmsMessage.barangay_id == user.barangay_id)
    rows = q.order_by(SmsMessage.id.desc()).limit(min(limit, 500)).all()
    return [{'id': m.id, 'phone': m.phone[:-4] + '****', 'body': m.body, 'kind': m.kind, 'status': m.status,
             'attempts': m.attempts, 'error': m.error,
             'created_at': m.created_at.isoformat() + 'Z', 'sent_at': m.sent_at.isoformat() + 'Z' if m.sent_at else None}
            for m in rows]


@router.get('/sms/status')
def sms_status(user=Depends(auth.get_current_user), db: Session = Depends(get_db)):
    counts = {s: db.query(SmsMessage).filter(SmsMessage.status == s).count() for s in ('queued', 'sending', 'sent', 'failed')}
    seen = _last_seen['at']
    return {'enabled': ENABLED, 'counts': counts,
            'device_online': bool(seen and datetime.utcnow() - seen < timedelta(seconds=30)),
            'device_last_seen': seen.isoformat() + 'Z' if seen else None}


class TestIn(BaseModel):
    phone: str


@router.post('/sms/test')
def sms_test(p: TestIn, user=Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if not _queue(db, p.phone, 'BilisLikas 2.0: Test message. Gumagana ang SMS alert sender.', 'test', user.barangay_id):
        raise HTTPException(status_code=422, detail='Enter a valid Philippine mobile number, e.g. 0917 123 4567.')
    db.commit()
    return {'queued': True}


# ---------- Live Evacuation page: status for one barangay and "send again" ----------
def _brgy_for(user, barangay_id):
    if _is_city(user):
        return barangay_id
    return user.barangay_id


def _active_incident(db, brgy_id):
    I = models.Incident
    return db.query(I).filter(I.barangay_id == brgy_id, I.ended_at.is_(None)).order_by(I.id.desc()).first()


def _inside_ids(db, brgy_id):
    """Residents whose latest record is a check-in (they are inside a center now)."""
    CR = models.CheckinRecord
    ids = set()
    for e in _residents(db, brgy_id):
        last = db.query(CR).filter(CR.evacuee_id == e.id).order_by(CR.id.desc()).first()
        if last is not None and last.event_type == 'check_in':
            ids.add(e.id)
    return ids


@router.get('/sms/barangay-status')
def sms_barangay_status(barangay_id: Optional[int] = None, user=Depends(auth.get_current_user), db: Session = Depends(get_db)):
    b = _brgy_for(user, barangay_id)
    i = _active_incident(db, b) if b else None
    q = db.query(SmsMessage).filter(SmsMessage.barangay_id == b)
    if i is not None:
        q = q.filter(SmsMessage.created_at >= i.started_at)
    rows = q.all()
    counts = {s: len([m for m in rows if m.status == s]) for s in ('queued', 'sending', 'sent', 'failed')}
    with_number = len({normalize(e.contact_number) for e in _residents(db, b) if normalize(e.contact_number)}) if b else 0
    last = max((m.sent_at for m in rows if m.status == 'sent' and m.sent_at), default=None)
    seen = _last_seen['at']
    return {'enabled': ENABLED, 'active': i is not None, 'counts': counts, 'total': len(rows), 'with_number': with_number,
            'last_sent': last.isoformat() + 'Z' if last else None,
            'device_online': bool(seen and datetime.utcnow() - seen < timedelta(seconds=30))}


class ResendIn(BaseModel):
    target: str = 'not_evacuated'      # not_evacuated | all
    message: Optional[str] = None
    barangay_id: Optional[int] = None


@router.post('/sms/resend')
def sms_resend(p: ResendIn, user=Depends(auth.get_current_user), db: Session = Depends(get_db)):
    b = _brgy_for(user, p.barangay_id)
    if not b:
        raise HTTPException(status_code=422, detail='Choose a barangay.')
    i = _active_incident(db, b)
    if i is None:
        raise HTTPException(status_code=409, detail='Start an evacuation first. Alerts can be sent again only while an evacuation is running.')
    recent = db.query(SmsMessage).filter(SmsMessage.barangay_id == b, SmsMessage.kind == 'evacuation_resend',
                                         SmsMessage.created_at >= datetime.utcnow() - timedelta(minutes=2)).first()
    if recent:
        raise HTTPException(status_code=429, detail='An alert was just sent. Wait 2 minutes before sending again.')
    brgy = db.get(models.Barangay, b)
    center = db.get(models.EvacuationCenter, i.evacuation_center_id) if i.evacuation_center_id else None
    body = ' '.join((p.message or '').split())[:300]
    if not body:
        body = ('PAALALA - BilisLikas 2.0, {b}: Patuloy po ang {d} evacuation. Kung hindi pa kayo nakalilikas, '
                'pumunta na po sa {w}. Humarap sa camera pagpasok.').format(
            b=brgy.name if brgy else 'Barangay', d=i.disaster_type,
            w=center.name if center else 'pinakamalapit na evacuation center')
    inside = _inside_ids(db, b) if p.target == 'not_evacuated' else set()
    by_phone = {}
    for e in _residents(db, b):
        ph = normalize(e.contact_number)
        if not ph:
            continue
        by_phone.setdefault(ph, []).append(e.id)
    n = 0
    for ph, ids in by_phone.items():
        if p.target == 'not_evacuated' and all(x in inside for x in ids):
            continue  # everyone using this number is already inside a center
        db.add(SmsMessage(phone=ph, body=body, kind='evacuation_resend', barangay_id=b))
        n += 1
    db.commit()
    return {'queued': n, 'target': p.target, 'message': body}
