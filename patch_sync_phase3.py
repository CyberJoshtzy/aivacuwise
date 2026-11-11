"""Cloud sync, Phase 3: the actual syncing.

- models.py: stamping is switched off while applying data from other servers, a sync_dirty flag marks
  records this server still has to send, and the hub keeps a sync_log of every change it received.
- main.py: POST /sync/push, GET /sync/pull (used on the hub), POST /sync/notify (refreshes open pages).

Run from ~/aivacuwise with the venv active:  python3 patch_sync_phase3.py
Safe to run twice.
"""
import shutil
import subprocess
import sys

P1 = '# ---- AiVacuwise: cloud sync phase 1 (sync-ready records) ----'
MARK = '# ---- AiVacuwise: cloud sync phase 3 (push, pull, notify) ----'
D = '_' * 2

models_src, main_src = open('models.py').read(), open('main.py').read()
new_models, new_main = models_src, main_src
report = []


def stop(msg):
    print('STOP: ' + msg)
    print('Nothing was changed.')
    sys.exit(1)


if P1 not in models_src or P1 not in main_src:
    stop('phase 1 not found. Install cloud sync phase 1 first.')

if MARK in models_src:
    report.append('models.py: phase 3 already there, skipped')
else:
    s = models_src
    swaps = [
        ("    _cls.origin = Column(String, nullable=True)\n",
         "    _cls.origin = Column(String, nullable=True)\n"
         "    _cls.sync_dirty = Column(Boolean, nullable=True, default=False, index=True)\n"),
        ("def _sync_on_insert(mapper, connection, target):\n"
         "    if not getattr(target, 'uuid', None):",
         "def _sync_importing(target):\n"
         "    s = _sync_object_session(target)\n"
         "    return bool(s is not None and s.info.get('sync_import'))\n\n\n"
         "def _sync_on_insert(mapper, connection, target):\n"
         "    if _sync_importing(target):\n"
         "        return\n"
         "    target.sync_dirty = True\n"
         "    if not getattr(target, 'uuid', None):"),
        ("def _sync_on_update(mapper, connection, target):\n"
         "    target.updated_at = datetime.utcnow()\n",
         "def _sync_on_update(mapper, connection, target):\n"
         "    if _sync_importing(target):\n"
         "        return\n"
         "    target.updated_at = datetime.utcnow()\n"
         "    target.sync_dirty = True\n"),
        ("def _sync_record_deletions(session, flush_context, instances):\n",
         "def _sync_record_deletions(session, flush_context, instances):\n"
         "    if session.info.get('sync_import'):\n"
         "        return\n"),
        ("from sqlalchemy.orm import Session as _SyncSession\n",
         "from sqlalchemy.orm import Session as _SyncSession\n"
         "from sqlalchemy.orm import object_session as _sync_object_session\n"),
    ]
    for a, b in swaps:
        if s.count(a) != 1:
            stop('models.py phase 1 code is not as expected near: ' + a.splitlines()[0])
        s = s.replace(a, b)
    s = s.rstrip() + '''


{MARK}
class SyncLog(Base):
    """On the cloud hub: every change received, in order, so each server can pull what it has not seen."""
    {D}tablename{D} = "sync_log"
    seq = Column(Integer, primary_key=True)
    table_name = Column(String, nullable=False)
    record_uuid = Column(String(36), nullable=False, index=True)
    is_tombstone = Column(Boolean, nullable=False, default=False)
    origin = Column(String, nullable=False, index=True)
    received_at = Column(DateTime, nullable=False, default=datetime.utcnow)
'''.format(MARK=MARK, D=D)
    new_models = s
    report.append('models.py: stamping pauses during sync imports; added sync_dirty and sync_log')

if MARK in main_src:
    report.append('main.py: phase 3 endpoints already there, skipped')
else:
    new_main = main_src.rstrip() + '''


{MARK}
import os as _sync_os
from fastapi import Header as _SyncHeader
from pydantic import BaseModel as _SyncBase
import sync_core


class SyncPushIn(_SyncBase):
    server_id: str
    rows: list = []
    tombstones: list = []


def _sync_check_key(key):
    expected = (_sync_os.getenv('SYNC_KEY') or '').strip()
    if not expected:
        raise HTTPException(status_code=503, detail='Sync is not configured on this server (SYNC_KEY missing).')
    if (key or '').strip() != expected:
        raise HTTPException(status_code=401, detail='Invalid sync key.')


@app.post('/sync/push')
def sync_push(payload: SyncPushIn, db: Session = Depends(get_db), x_sync_key: str = _SyncHeader(None)):
    """Cloud hub: receive changes from one barangay server."""
    _sync_check_key(x_sync_key)
    applied, skipped, aliased, waiting = sync_core.apply_rows(db, payload.rows)
    removed = sync_core.apply_tombstones(db, payload.tombstones)
    for table, uuid in applied:
        db.add(models.SyncLog(table_name=table, record_uuid=uuid, is_tombstone=False, origin=payload.server_id))
    for t in payload.tombstones:
        if t.get('table') in sync_core.BY_TABLE and t.get('uuid'):
            db.add(models.SyncLog(table_name=t['table'], record_uuid=t['uuid'], is_tombstone=True, origin=payload.server_id))
    db.commit()
    db.info.pop('sync_import', None)
    return {{'applied': [u for _t, u in applied], 'skipped': skipped, 'aliased': aliased,
            'waiting': waiting, 'removed': [u for _t, u in removed]}}


@app.get('/sync/pull')
def sync_pull(since: int = 0, exclude_origin: str = '', limit: int = 300,
              db: Session = Depends(get_db), x_sync_key: str = _SyncHeader(None)):
    """Cloud hub: changes from all other servers since the given position."""
    _sync_check_key(x_sync_key)
    q = db.query(models.SyncLog).filter(models.SyncLog.seq > since)
    if exclude_origin:
        q = q.filter(models.SyncLog.origin != exclude_origin)
    entries = q.order_by(models.SyncLog.seq).limit(max(1, min(limit, 1000))).all()
    latest = {{}}
    for e in entries:  # keep only the newest entry for each record (a deletion beats an older update)
        latest[e.record_uuid] = e
    rows, tombstones, cache = [], [], {{}}
    for e in sorted(latest.values(), key=lambda x: x.seq):
        if e.is_tombstone:
            tombstones.append({{'table': e.table_name, 'uuid': e.record_uuid}})
            continue
        cls = sync_core.BY_TABLE.get(e.table_name, (None,))[0]
        obj = db.query(cls).filter(cls.uuid == e.record_uuid).first() if cls else None
        if obj is not None:
            rows.append(sync_core.serialize(db, obj, cache))
    last = db.query(func.max(models.SyncLog.seq)).scalar() or 0
    nxt = entries[-1].seq if entries else since
    return {{'rows': rows, 'tombstones': tombstones, 'next': nxt, 'more': nxt < last and len(entries) > 0}}


@app.post('/sync/notify')
async def sync_notify(x_sync_key: str = _SyncHeader(None), db: Session = Depends(get_db)):
    """Local server: the sync agent calls this after applying new data, so open pages refresh."""
    _sync_check_key(x_sync_key)
    for b in db.query(models.Barangay).all():
        await manager.broadcast({{'type': 'sync_update', 'barangay_id': b.id}})
    return {{'ok': True}}
'''.format(MARK=MARK)
    report.append('main.py: added POST /sync/push, GET /sync/pull, POST /sync/notify')

changed = []
for name, old, new in [('models.py', models_src, new_models), ('main.py', main_src, new_main)]:
    if new != old:
        shutil.copy(name, name + '.bak_sync3')
        open(name, 'w').write(new)
        changed.append((name, old))
r = subprocess.run([sys.executable, '-m', 'py_compile', 'models.py', 'main.py', 'sync_core.py'], capture_output=True, text=True)
if r.returncode != 0:
    for name, old in changed:
        open(name, 'w').write(old)
    print(r.stderr)
    stop('syntax check failed, original files restored')
for line in report:
    print('OK  ' + line)
print('All files compile.' + (' Backups saved as *.bak_sync3' if changed else ''))
