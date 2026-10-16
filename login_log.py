"""BilisLikas 2.0: sign-in history of every account.

- Table login_logs (created on startup): time, user, email typed, result, IP address, device.
- record(...) is called by /login in main.py for every attempt (success, wrong password, blocked).
- GET /admin/login_logs   System Administrator only; newest first, up to 1000 rows.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, insert, select
from sqlalchemy.orm import Session

import auth
import models
from database import get_db, engine

router = APIRouter()
_meta = MetaData()
logs = Table('login_logs', _meta,
             Column('id', Integer, primary_key=True),
             Column('time', DateTime, nullable=False, index=True),
             Column('user_id', Integer, nullable=True, index=True),
             Column('identifier', String, nullable=True),
             Column('result', String, nullable=False),
             Column('detail', String, nullable=True),
             Column('ip', String, nullable=True),
             Column('device', String, nullable=True))
try:
    _meta.create_all(engine)
except Exception as exc:
    print('login_log: could not create table:', exc)


def _device(ua):
    ua = ua or ''
    os_ = 'Android' if 'Android' in ua else 'iPhone' if 'iPhone' in ua else 'Windows' if 'Windows' in ua else 'macOS' if 'Mac OS' in ua else 'Linux' if 'Linux' in ua else 'Unknown'
    br = 'Edge' if 'Edg/' in ua else 'Chrome' if 'Chrome/' in ua else 'Firefox' if 'Firefox/' in ua else 'Safari' if 'Safari/' in ua else 'Other'
    return br + ' on ' + os_


def record(db, request, user, identifier, result, detail=None):
    try:
        ip = None
        if request is not None:
            ip = request.headers.get('x-forwarded-for', '').split(',')[0].strip() or (request.client.host if request.client else None)
        db.execute(insert(logs).values(time=datetime.utcnow(), user_id=user.id if user else None,
                                       identifier=(identifier or '')[:200], result=result, detail=detail, ip=ip,
                                       device=_device(request.headers.get('user-agent') if request is not None else '')))
        db.commit()
    except Exception as exc:
        db.rollback()
        print('login_log: could not record:', exc)


@router.get('/admin/login_logs')
def login_logs(user_id: Optional[int] = None, user=Depends(auth.get_current_user), db: Session = Depends(get_db)):
    role = user.role.value if hasattr(user.role, 'value') else user.role
    if role != 'city_admin' or not getattr(user, 'is_superuser', False):
        raise HTTPException(status_code=403, detail='Only the City System Administrator can view the sign-in history.')
    q = select(logs).order_by(logs.c.time.desc()).limit(1000)
    if user_id:
        q = q.where(logs.c.user_id == user_id)
    users = {u.id: u for u in db.query(models.User).all()}
    brgy = {b.id: b.name for b in db.query(models.Barangay).all()}
    out = []
    for r in db.execute(q).mappings():
        u = users.get(r['user_id'])
        urole = (u.role.value if hasattr(u.role, 'value') else u.role) if u else None
        out.append({'id': r['id'], 'time': r['time'].isoformat() + 'Z', 'user_id': r['user_id'],
                    'name': (u.full_name or u.email) if u else None, 'email': u.email if u else r['identifier'],
                    'where': ('City Hall' if urole == 'city_admin' else brgy.get(u.barangay_id, '-')) if u else 'Unknown account',
                    'position': (u.designation or '-') if u else '-',
                    'result': r['result'], 'detail': r['detail'], 'ip': r['ip'], 'device': r['device']})
    return out
