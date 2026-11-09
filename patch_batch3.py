"""Batch 3 backend: evacuation incidents (start/end with a disaster type) and barangay edit/delete.

Run from ~/bilislikas2.0 with the venv active:  python3 patch_batch3.py
Then create the new table in PostgreSQL:        python3 create_new_tables.py
Safe to run twice.
"""
import re
import shutil
import subprocess
import sys

D = '_' * 2
MARK = '# ---- Ai-Vacuwise: incidents and barangay edit/delete (batch 3) ----'
BATCH2 = '# ---- Ai-Vacuwise: edit and delete endpoints (batch 2) ----'

models_src = open('models.py').read()
main_src = open('main.py').read()
new_models, new_main = models_src, main_src
report = []


def stop(msg):
    print('STOP: ' + msg)
    print('Nothing was changed.')
    sys.exit(1)


if BATCH2 not in main_src:
    stop('batch 2 endpoints not found in main.py. Run patch_edit_delete.py first.')

# ---------- models.py: Incident table ----------
if re.search(D + r'tablename' + D + r'\s*=\s*["\']incidents["\']', models_src):
    report.append('models.py: incidents table already there, skipped')
else:
    if not re.search(r'^Base\s*=|import .*\bBase\b', models_src, re.M):
        stop('could not find Base in models.py')
    needed = ['Column', 'Integer', 'String', 'DateTime', 'ForeignKey']
    missing = [n for n in needed if not re.search(r'\b' + n + r'\b', models_src.split('class ')[0])]
    header = ('from sqlalchemy import ' + ', '.join(missing) + '\n') if missing else ''
    cls = (
        '\n\nclass Incident(Base):\n'
        '    ' + D + 'tablename' + D + ' = "incidents"\n'
        '    id = Column(Integer, primary_key=True, index=True)\n'
        '    barangay_id = Column(Integer, ForeignKey("barangays.id"), nullable=False)\n'
        '    evacuation_center_id = Column(Integer, ForeignKey("evacuation_centers.id"), nullable=True)\n'
        '    disaster_type = Column(String, nullable=False)\n'
        '    started_at = Column(DateTime, nullable=False)\n'
        '    ended_at = Column(DateTime, nullable=True)\n'
        '    started_by = Column(Integer, ForeignKey("users.id"), nullable=True)\n'
        '    ended_by = Column(Integer, ForeignKey("users.id"), nullable=True)\n'
    )
    new_models = header + models_src.rstrip() + cls
    report.append('models.py: added Incident model (table "incidents")' + (' and imports ' + ', '.join(missing) if missing else ''))

# ---------- main.py: endpoints ----------
if MARK in main_src:
    report.append('main.py: batch 3 endpoints already there, skipped')
else:
    getdb = 'get_db' if re.search(r'^from database import .*\bget_db\b', main_src, re.M) else 'database.get_db'
    code = '''

{MARK}
from datetime import datetime as _BL3dt
from sqlalchemy import func as _BL3func

BL_DISASTERS = ['Fire', 'Earthquake', 'Flood', 'Typhoon', 'Landslide', 'Other']


class BLIncidentStart(_BLBaseModel):
    disaster_type: str
    evacuation_center_id: _BLOptional[int] = None
    barangay_id: _BLOptional[int] = None


class BLBarangayUpdate(_BLBaseModel):
    name: str


def _bl_iso(dt):
    return dt.isoformat() if dt is not None else None


def _bl_incident_dict(i):
    return {{
        'id': i.id, 'barangay_id': i.barangay_id, 'evacuation_center_id': i.evacuation_center_id,
        'disaster_type': i.disaster_type, 'started_at': _bl_iso(i.started_at), 'ended_at': _bl_iso(i.ended_at),
        'started_by': i.started_by, 'ended_by': i.ended_by, 'active': i.ended_at is None,
    }}


@app.get('/incidents')
def bl_list_incidents(active: bool = False, db: _BLSession = _BLDepends({GETDB}),
                      user=_BLDepends(auth.get_current_user)):
    Incident = _bl_model('incidents')
    q = db.query(Incident)
    if user.role != 'city_admin':
        q = q.filter(Incident.barangay_id == user.barangay_id)
    if active:
        q = q.filter(Incident.ended_at.is_(None))
    return [_bl_incident_dict(i) for i in q.order_by(Incident.id.desc()).limit(50).all()]


@app.post('/incidents')
async def bl_start_incident(payload: BLIncidentStart, db: _BLSession = _BLDepends({GETDB}),
                            user=_BLDepends(auth.get_current_user)):
    Incident = _bl_model('incidents')
    brgy_id = payload.barangay_id if user.role == 'city_admin' else user.barangay_id
    if brgy_id is None:
        raise _BLHTTPException(status_code=422, detail='Choose which barangay is evacuating.')
    if db.query(_bl_model('barangays')).filter_by(id=brgy_id).first() is None:
        raise _BLHTTPException(status_code=404, detail='Barangay not found.')
    kind = (payload.disaster_type or '').strip().capitalize()
    if kind not in BL_DISASTERS:
        raise _BLHTTPException(status_code=422, detail='Disaster type must be one of: ' + ', '.join(BL_DISASTERS) + '.')
    if payload.evacuation_center_id is not None and db.query(_bl_model('evacuation_centers')).filter_by(id=payload.evacuation_center_id).first() is None:
        raise _BLHTTPException(status_code=404, detail='Evacuation center not found.')
    if db.query(Incident).filter(Incident.barangay_id == brgy_id, Incident.ended_at.is_(None)).first():
        raise _BLHTTPException(status_code=409, detail='An evacuation is already active for this barangay. End it before starting a new one.')
    i = Incident(barangay_id=brgy_id, evacuation_center_id=payload.evacuation_center_id, disaster_type=kind,
                 started_at=_BL3dt.utcnow(), started_by=user.id)
    db.add(i)
    db.commit()
    db.refresh(i)
    await _bl_notify(brgy_id)
    return _bl_incident_dict(i)


@app.post('/incidents/{{incident_id}}/end')
async def bl_end_incident(incident_id: int, db: _BLSession = _BLDepends({GETDB}),
                          user=_BLDepends(auth.get_current_user)):
    Incident = _bl_model('incidents')
    i = db.query(Incident).filter(Incident.id == incident_id).first()
    if not i:
        raise _BLHTTPException(status_code=404, detail='Evacuation not found.')
    if not _bl_can_edit(user, i.barangay_id):
        raise _BLHTTPException(status_code=403, detail='You can only end your own barangay\\'s evacuation.')
    if i.ended_at is not None:
        raise _BLHTTPException(status_code=409, detail='This evacuation has already ended.')
    i.ended_at = _BL3dt.utcnow()
    i.ended_by = user.id
    db.commit()
    db.refresh(i)
    await _bl_notify(i.barangay_id)
    return _bl_incident_dict(i)


@app.put('/barangays/{{barangay_id}}')
async def bl_update_barangay(barangay_id: int, payload: BLBarangayUpdate, db: _BLSession = _BLDepends({GETDB}),
                             user=_BLDepends(auth.get_current_user)):
    Barangay = _bl_model('barangays')
    b = db.query(Barangay).filter(Barangay.id == barangay_id).first()
    if not b:
        raise _BLHTTPException(status_code=404, detail='Barangay not found.')
    if not _bl_can_edit(user, barangay_id):
        raise _BLHTTPException(status_code=403, detail='You can only edit your own barangay.')
    name = (payload.name or '').strip()
    if not name:
        raise _BLHTTPException(status_code=422, detail='Barangay name cannot be empty.')
    clash = db.query(Barangay).filter(_BL3func.lower(Barangay.name) == name.lower(), Barangay.id != barangay_id).first()
    if clash:
        raise _BLHTTPException(status_code=409, detail='Another barangay already uses this name.')
    b.name = name
    db.commit()
    await _bl_notify(barangay_id)
    return {{'id': b.id, 'name': b.name}}


@app.delete('/barangays/{{barangay_id}}')
async def bl_delete_barangay(barangay_id: int, db: _BLSession = _BLDepends({GETDB}),
                             user=_BLDepends(auth.get_current_user)):
    if user.role != 'city_admin':
        raise _BLHTTPException(status_code=403, detail='Only the City Admin can delete a barangay.')
    Barangay = _bl_model('barangays')
    b = db.query(Barangay).filter(Barangay.id == barangay_id).first()
    if not b:
        raise _BLHTTPException(status_code=404, detail='Barangay not found.')
    links = [
        ('evacuation centers', _bl_model('evacuation_centers'), 'barangay_id'),
        ('registered evacuees', _bl_model('evacuees'), 'registered_barangay_id'),
        ('user accounts', _bl_model('users'), 'barangay_id'),
        ('households', _bl_model('households'), 'registered_barangay_id'),
        ('evacuation records', _bl_model('incidents'), 'barangay_id'),
    ]
    found = []
    for label, M, col in links:
        n = db.query(M).filter(getattr(M, col) == barangay_id).count()
        if n:
            found.append('%d %s' % (n, label))
    if found:
        raise _BLHTTPException(status_code=409, detail='This barangay still has ' + ', '.join(found) + '. Remove or move them first.')
    db.delete(b)
    db.commit()
    return {{'deleted': barangay_id}}
'''.format(MARK=MARK, GETDB=getdb)
    new_main = main_src.rstrip() + '\n' + code
    report.append('main.py: added GET/POST /incidents, POST /incidents/{id}/end, PUT and DELETE /barangays/{id}')

# ---------- write, compile, restore on failure ----------
changed = []
for name, old, new in [('models.py', models_src, new_models), ('main.py', main_src, new_main)]:
    if new != old:
        shutil.copy(name, name + '.bak_batch3')
        open(name, 'w').write(new)
        changed.append((name, old))
r = subprocess.run([sys.executable, '-m', 'py_compile', 'models.py', 'main.py'], capture_output=True, text=True)
if r.returncode != 0:
    for name, old in changed:
        open(name, 'w').write(old)
    print(r.stderr)
    stop('syntax check failed, original files restored')
for line in report:
    print('OK  ' + line)
print('All files compile.' + (' Backups saved as *.bak_batch3' if changed else ''))
