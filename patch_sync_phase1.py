"""Cloud sync, Phase 1: make the database sync-ready (no sync happens yet).

Run from ~/bilislikas2.0 with the venv active:  python3 patch_sync_phase1.py
Then (with the service STOPPED):              python3 migrate_sync_phase1.py
Safe to run twice.
"""
import re
import shutil
import subprocess
import sys

MARK = '# ---- Ai-Vacuwise: cloud sync phase 1 (sync-ready records) ----'
D = '_' * 2  # double underscore, written this way so pasting never corrupts it

files = {f: open(f).read() for f in ['models.py', 'database.py', 'schemas.py', 'main.py']}
new = dict(files)
report = []


def stop(msg):
    print('STOP: ' + msg)
    print('Nothing was changed.')
    sys.exit(1)


# ---------- models.py: columns added to every synced table, tombstones, automatic stamping ----------
if MARK in files['models.py']:
    report.append('models.py: phase 1 already there, skipped')
else:
    block = '''

{MARK}
import os as _sync_os
import uuid as _sync_uuid
from sqlalchemy import event as _sync_event
from sqlalchemy.orm import Session as _SyncSession

SERVER_ID = _sync_os.getenv('BILISLIKAS_SERVER_ID', 'local')

SYNCED_MODELS = [Barangay, EvacuationCenter, User, Household, Evacuee, CheckinRecord,
                 Transfer, Tracker, TrackerPing, GpsPing, Incident]

for _cls in SYNCED_MODELS:
    _cls.uuid = Column(String(36), unique=True, index=True, nullable=True)
    _cls.updated_at = Column(DateTime, nullable=True, index=True)
    _cls.origin = Column(String, nullable=True)

Barangay.district = Column(String, nullable=True)


class SyncTombstone(Base):
    {D}tablename{D} = "sync_tombstones"
    id = Column(Integer, primary_key=True)
    table_name = Column(String, nullable=False)
    record_uuid = Column(String(36), nullable=False, index=True)
    deleted_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    origin = Column(String, nullable=True)


class SyncState(Base):
    {D}tablename{D} = "sync_state"
    key = Column(String, primary_key=True)
    value = Column(String, nullable=True)


def _sync_on_insert(mapper, connection, target):
    if not getattr(target, 'uuid', None):
        target.uuid = str(_sync_uuid.uuid4())
    if not getattr(target, 'origin', None):
        target.origin = SERVER_ID
    target.updated_at = datetime.utcnow()


def _sync_on_update(mapper, connection, target):
    target.updated_at = datetime.utcnow()


for _cls in SYNCED_MODELS:
    _sync_event.listen(_cls, 'before_insert', _sync_on_insert)
    _sync_event.listen(_cls, 'before_update', _sync_on_update)


@_sync_event.listens_for(_SyncSession, 'before_flush')
def _sync_record_deletions(session, flush_context, instances):
    for obj in list(session.deleted):
        if type(obj) in SYNCED_MODELS and getattr(obj, 'uuid', None):
            session.add(SyncTombstone(table_name=obj.{D}tablename{D}, record_uuid=obj.uuid,
                                      deleted_at=datetime.utcnow(), origin=SERVER_ID))
'''.format(MARK=MARK, D=D)
    new['models.py'] = files['models.py'].rstrip() + '\n' + block
    report.append('models.py: added uuid, updated_at, origin to 11 tables; district; sync_tombstones; sync_state; automatic stamping')

# ---------- database.py: host and port from .env (defaults unchanged) ----------
s = new['database.py']
if 'POSTGRES_HOST' in s:
    report.append('database.py: already reads host/port from .env, skipped')
else:
    a, b = 'DB_HOST = "127.0.0.1"', 'DB_PORT = "5432"'
    if s.count(a) != 1 or s.count(b) != 1:
        stop('database.py does not have the expected DB_HOST / DB_PORT lines')
    s = s.replace(a, 'DB_HOST = os.getenv("POSTGRES_HOST", "127.0.0.1")').replace(b, 'DB_PORT = os.getenv("POSTGRES_PORT", "5432")')
    new['database.py'] = s
    report.append('database.py: DB_HOST and DB_PORT now come from .env (default 127.0.0.1:5432, unchanged)')

# ---------- schemas.py: EvacueeOut includes household fields (fixes "Household: None") ----------
s = new['schemas.py']
old = 'class EvacueeOut(EvacueeCreate):\n    id: int\n'
if 'household_id: Optional[int] = None\n    is_head_of_family' in s:
    report.append('schemas.py: EvacueeOut already has household fields, skipped')
elif s.count(old) != 1:
    stop('could not find EvacueeOut in schemas.py')
else:
    new['schemas.py'] = s.replace(old, old + '    household_id: Optional[int] = None\n    is_head_of_family: Optional[bool] = False\n')
    report.append('schemas.py: EvacueeOut now includes household_id and is_head_of_family')

# ---------- main.py: GET /sync/status ----------
s = new['main.py']
if MARK in s:
    report.append('main.py: /sync/status already there, skipped')
else:
    new['main.py'] = s.rstrip() + '''

{MARK}
@app.get('/sync/status')
def sync_status(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    counts = {{}}
    for cls in models.SYNCED_MODELS:
        counts[cls.{D}tablename{D}] = {{
            'records': db.query(cls).count(),
            'missing_uuid': db.query(cls).filter(cls.uuid.is_(None)).count(),
        }}
    state = {{r.key: r.value for r in db.query(models.SyncState).all()}}
    return {{
        'server_id': models.SERVER_ID,
        'tables': counts,
        'tombstones': db.query(models.SyncTombstone).count(),
        'sync_state': state,
    }}
'''.format(MARK=MARK, D=D)
    report.append('main.py: added GET /sync/status')

changed = []
for f in files:
    if new[f] != files[f]:
        shutil.copy(f, f + '.bak_sync1')
        open(f, 'w').write(new[f])
        changed.append(f)
r = subprocess.run([sys.executable, '-m', 'py_compile'] + list(files), capture_output=True, text=True)
if r.returncode != 0:
    for f in changed:
        open(f, 'w').write(files[f])
    print(r.stderr)
    stop('syntax check failed, original files restored')
for line in report:
    print('OK  ' + line)
print('All files compile.' + (' Backups saved as *.bak_sync1' if changed else ''))
