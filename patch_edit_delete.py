"""Adds Edit and Delete endpoints for evacuees and evacuation centers to main.py.

Run from ~/bilislikas2.0 with the venv active:  python3 patch_edit_delete.py
Safe to run twice: it skips itself if the endpoints are already there.
"""
import re
import shutil
import subprocess
import sys

MARK = '# ---- Ai-Vacuwise: edit and delete endpoints (batch 2) ----'

src = open('main.py').read()
if MARK in src:
    print('OK  Edit and delete endpoints are already in main.py. Nothing to do.')
    sys.exit(0)

# The appended code must reuse main.py's own names. Check they exist first.
guard = 'if ' + '_' * 2 + 'name' + '_' * 2
if guard in src:
    print('STOP: main.py has a "if name == main" block at the end. Send me its last 10 lines. Nothing changed.')
    sys.exit(1)
if 'auth.get_current_user' not in src:
    print('STOP: main.py does not use auth.get_current_user. Nothing changed.')
    sys.exit(1)
if re.search(r'^from database import .*\bget_db\b', src, re.M):
    getdb = 'get_db'
elif 'database.get_db' in src:
    getdb = 'database.get_db'
else:
    print('STOP: could not find how main.py imports get_db. Nothing changed.')
    sys.exit(1)
notify = ("        await manager.broadcast({'type': 'records_update', 'barangay_id': barangay_id})"
          if 'manager.broadcast' in src else '        pass')
occ_helper = '_get_current_evacuees_at_center' in src

code = '''

{MARK}
from datetime import date as _BLDate
from typing import Optional as _BLOptional
from fastapi import Depends as _BLDepends, HTTPException as _BLHTTPException
from pydantic import BaseModel as _BLBaseModel
from sqlalchemy import String as _BLString
from sqlalchemy.orm import Session as _BLSession


def _bl_model(table):
    key = '_' * 2 + 'tablename' + '_' * 2
    for obj in vars(models).values():
        if isinstance(obj, type) and getattr(obj, key, None) == table:
            return obj
    raise RuntimeError('No model found for table ' + table)


class BLEvacueeUpdate(_BLBaseModel):
    full_name: _BLOptional[str] = None
    birthdate: _BLOptional[_BLDate] = None
    sex: _BLOptional[str] = None
    address: _BLOptional[str] = None
    contact_number: _BLOptional[str] = None


class BLCenterUpdate(_BLBaseModel):
    name: _BLOptional[str] = None
    address: _BLOptional[str] = None
    capacity: _BLOptional[int] = None


def _bl_can_edit(user, barangay_id):
    return user.role == 'city_admin' or (barangay_id is not None and user.barangay_id == barangay_id)


async def _bl_notify(barangay_id):
    try:
{NOTIFY}
    except Exception:
        pass


def _bl_evacuee_dict(e):
    return {{
        'id': e.id, 'full_name': e.full_name,
        'birthdate': str(e.birthdate) if e.birthdate is not None else None,
        'sex': e.sex, 'address': e.address, 'contact_number': e.contact_number,
        'registered_barangay_id': e.registered_barangay_id,
        'identification_method': e.identification_method,
        'household_id': e.household_id, 'is_head_of_family': e.is_head_of_family,
    }}


def _bl_occupancy(db, center_id):
{OCC}


@app.put('/evacuees/{{evacuee_id}}')
async def bl_update_evacuee(evacuee_id: int, payload: BLEvacueeUpdate,
                            db: _BLSession = _BLDepends({GETDB}),
                            user=_BLDepends(auth.get_current_user)):
    Evacuee = _bl_model('evacuees')
    e = db.query(Evacuee).filter(Evacuee.id == evacuee_id).first()
    if not e:
        raise _BLHTTPException(status_code=404, detail='Evacuee not found.')
    if not _bl_can_edit(user, e.registered_barangay_id):
        raise _BLHTTPException(status_code=403, detail='You can only edit residents of your own barangay.')
    data = payload.model_dump(exclude_unset=True)
    if 'full_name' in data and not (data['full_name'] or '').strip():
        raise _BLHTTPException(status_code=422, detail='Full name cannot be empty.')
    birth_is_text = isinstance(Evacuee.birthdate.property.columns[0].type, _BLString)
    for key, value in data.items():
        if key == 'birthdate' and value is not None and birth_is_text:
            value = value.isoformat()
        if isinstance(value, str):
            value = value.strip()
        setattr(e, key, value)
    db.commit()
    db.refresh(e)
    await _bl_notify(e.registered_barangay_id)
    return _bl_evacuee_dict(e)


@app.delete('/evacuees/{{evacuee_id}}')
async def bl_delete_evacuee(evacuee_id: int,
                            db: _BLSession = _BLDepends({GETDB}),
                            user=_BLDepends(auth.get_current_user)):
    Evacuee = _bl_model('evacuees')
    e = db.query(Evacuee).filter(Evacuee.id == evacuee_id).first()
    if not e:
        raise _BLHTTPException(status_code=404, detail='Evacuee not found.')
    if not _bl_can_edit(user, e.registered_barangay_id):
        raise _BLHTTPException(status_code=403, detail='You can only delete residents of your own barangay.')
    Tracker = _bl_model('trackers')
    Household = _bl_model('households')
    Transfer = _bl_model('transfers')
    Checkin = _bl_model('checkin_records')
    db.query(Tracker).filter(Tracker.assigned_evacuee_id == e.id).update({{Tracker.assigned_evacuee_id: None}}, synchronize_session=False)
    db.query(Household).filter(Household.head_of_family_evacuee_id == e.id).update({{Household.head_of_family_evacuee_id: None}}, synchronize_session=False)
    db.query(Transfer).filter(Transfer.evacuee_id == e.id).delete(synchronize_session=False)
    db.query(Checkin).filter(Checkin.evacuee_id == e.id).delete(synchronize_session=False)
    barangay_id = e.registered_barangay_id
    db.delete(e)
    db.commit()
    await _bl_notify(barangay_id)
    return {{'deleted': evacuee_id}}


@app.put('/evacuation_centers/{{center_id}}')
async def bl_update_center(center_id: int, payload: BLCenterUpdate,
                           db: _BLSession = _BLDepends({GETDB}),
                           user=_BLDepends(auth.get_current_user)):
    Center = _bl_model('evacuation_centers')
    c = db.query(Center).filter(Center.id == center_id).first()
    if not c:
        raise _BLHTTPException(status_code=404, detail='Evacuation center not found.')
    if not _bl_can_edit(user, c.barangay_id):
        raise _BLHTTPException(status_code=403, detail='You can only edit your own barangay\\'s centers.')
    data = payload.model_dump(exclude_unset=True)
    if 'name' in data and not (data['name'] or '').strip():
        raise _BLHTTPException(status_code=422, detail='Center name cannot be empty.')
    if 'capacity' in data:
        if data['capacity'] is None or data['capacity'] < 1:
            raise _BLHTTPException(status_code=422, detail='Capacity must be at least 1.')
        occ = _bl_occupancy(db, c.id)
        if data['capacity'] < occ:
            raise _BLHTTPException(status_code=409, detail='Capacity cannot be lower than the %d evacuees inside right now.' % occ)
    for key, value in data.items():
        setattr(c, key, value.strip() if isinstance(value, str) else value)
    db.commit()
    db.refresh(c)
    await _bl_notify(c.barangay_id)
    return {{'id': c.id, 'name': c.name, 'address': c.address, 'capacity': c.capacity, 'barangay_id': c.barangay_id}}


@app.delete('/evacuation_centers/{{center_id}}')
async def bl_delete_center(center_id: int,
                           db: _BLSession = _BLDepends({GETDB}),
                           user=_BLDepends(auth.get_current_user)):
    Center = _bl_model('evacuation_centers')
    c = db.query(Center).filter(Center.id == center_id).first()
    if not c:
        raise _BLHTTPException(status_code=404, detail='Evacuation center not found.')
    if not _bl_can_edit(user, c.barangay_id):
        raise _BLHTTPException(status_code=403, detail='You can only delete your own barangay\\'s centers.')
    occ = _bl_occupancy(db, c.id)
    if occ > 0:
        raise _BLHTTPException(status_code=409, detail='%d evacuees are inside this center. Transfer them to another center before deleting it.' % occ)
    Checkin = _bl_model('checkin_records')
    Transfer = _bl_model('transfers')
    used = db.query(Checkin).filter(Checkin.evacuation_center_id == c.id).first() is not None
    used = used or db.query(Transfer).filter((Transfer.from_center_id == c.id) | (Transfer.to_center_id == c.id)).first() is not None
    try:
        Ping = _bl_model('tracker_pings')
        used = used or db.query(Ping).filter(Ping.evacuation_center_id == c.id).first() is not None
    except RuntimeError:
        pass
    if used:
        raise _BLHTTPException(status_code=409, detail='This center has check-in or transfer history, so it is kept for the records and cannot be deleted.')
    barangay_id = c.barangay_id
    db.delete(c)
    db.commit()
    await _bl_notify(barangay_id)
    return {{'deleted': center_id}}
'''

occ_body = ('    return len(_get_current_evacuees_at_center(db, center_id))' if occ_helper else
            '    return 0')
code = code.format(MARK=MARK, NOTIFY=notify, GETDB=getdb, OCC=occ_body)

shutil.copy('main.py', 'main.py.bak_editdelete')
open('main.py', 'w').write(src.rstrip() + '\n' + code)
r = subprocess.run([sys.executable, '-m', 'py_compile', 'main.py'], capture_output=True, text=True)
if r.returncode != 0:
    shutil.copy('main.py.bak_editdelete', 'main.py')
    print(r.stderr)
    print('STOP: syntax check failed, main.py restored. Nothing changed.')
    sys.exit(1)
print('OK  Added PUT and DELETE for /evacuees/{id} and /evacuation_centers/{id}')
print('OK  Live updates: ' + ('yes' if 'manager.broadcast' in src else 'no (manager.broadcast not found)'))
print('OK  Occupancy check: ' + ('yes' if occ_helper else 'no (helper not found)'))
print('main.py compiles. Backup saved as main.py.bak_editdelete')
