"""Cloud sync, Phase 4: sync status for the pages, and City of Manila districts.

- GET /sync/info: what the sidebar badge shows (last sync, changes waiting, or hub summary)
- GET /districts and PUT /barangays/{id}/district (City Admin only)
- Barangays now report their district; registration can include it.

Run from ~/bilislikas2.0 with the venv active:  python3 patch_sync_phase4.py   (no migration needed)
Safe to run twice.
"""
import re
import shutil
import subprocess
import sys

P3 = '# ---- Ai-Vacuwise: cloud sync phase 3 (push, pull, notify) ----'
MARK = '# ---- Ai-Vacuwise: cloud sync phase 4 (status and districts) ----'

main_src, schemas_src = open('main.py').read(), open('schemas.py').read()
new_main, new_schemas = main_src, schemas_src
report = []


def stop(msg):
    print('STOP: ' + msg)
    print('Nothing was changed.')
    sys.exit(1)


if P3 not in main_src:
    stop('cloud sync phase 3 not found in main.py. Install phase 3 first.')

# schemas.py: barangays report their district
old = 'class BarangayOut(BarangayCreate):\n    id: int\n'
if 'class BarangayOut(BarangayCreate):\n    id: int\n    district' in schemas_src:
    report.append('schemas.py: BarangayOut already has district, skipped')
elif schemas_src.count(old) != 1:
    stop('could not find BarangayOut in schemas.py')
else:
    new_schemas = schemas_src.replace(old, old + '    district: Optional[str] = None\n')
    report.append('schemas.py: BarangayOut now includes district')

if MARK in main_src:
    report.append('main.py: phase 4 already there, skipped')
else:
    s = main_src
    # Registration: optional district
    a = "    registration_code: _BLOptional[str] = None\n"
    if s.count(a) != 1:
        stop('could not find the registration form fields (batch 6)')
    s = s.replace(a, a + "    district: _BLOptional[str] = None\n")
    a = "        b = Barangay(name=name)\n"
    if s.count(a) != 1:
        stop('could not find where registration creates a barangay (batch 6)')
    s = s.replace(a, "        b = Barangay(name=name, district=payload.district if payload.district in MANILA_DISTRICTS else None)\n")
    s = s.rstrip() + '''


{MARK}
MANILA_DISTRICTS = ['Binondo', 'Ermita', 'Intramuros', 'Malate', 'Paco', 'Pandacan', 'Port Area', 'Quiapo',
                    'Sampaloc', 'San Andres', 'San Miguel', 'San Nicolas', 'Santa Ana', 'Santa Cruz',
                    'Santa Mesa', 'Tondo']


class BLDistrict(_BLBaseModel):
    district: _BLOptional[str] = None


@app.get('/districts')
def list_districts():
    return MANILA_DISTRICTS


@app.put('/barangays/{{barangay_id}}/district')
async def set_barangay_district(barangay_id: int, payload: BLDistrict, db: Session = Depends(get_db),
                                current_user=Depends(auth.get_current_user)):
    if current_user.role != 'city_admin':
        raise HTTPException(status_code=403, detail='Only the City Admin can set a barangay\\'s district.')
    b = db.query(models.Barangay).filter(models.Barangay.id == barangay_id).first()
    if not b:
        raise HTTPException(status_code=404, detail='Barangay not found.')
    d = (payload.district or '').strip() or None
    if d is not None and d not in MANILA_DISTRICTS:
        raise HTTPException(status_code=422, detail='Choose one of the 16 districts of Manila.')
    b.district = d
    db.commit()
    await _bl_notify(barangay_id)
    return {{'id': b.id, 'name': b.name, 'district': b.district}}


@app.get('/sync/info')
def sync_info(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    """Small summary for the sidebar badge."""
    st = {{r.key: r.value for r in db.query(models.SyncState).all()}}
    hub_rows = db.query(models.SyncLog.origin, func.max(models.SyncLog.received_at), func.count(models.SyncLog.seq)) \\
        .group_by(models.SyncLog.origin).all()
    if hub_rows:  # this server receives data from others: it is the cloud hub
        return {{'role': 'hub', 'server_id': models.SERVER_ID,
                'servers': [{{'server_id': o, 'last_received_at': _bl_iso(t), 'changes': n}} for o, t, n in hub_rows]}}
    waiting = sum(db.query(cls).filter(cls.sync_dirty.is_(True)).count() for cls in models.SYNCED_MODELS)
    last_t = int(st.get('push_tombstone_id', '0') or 0)
    waiting += db.query(models.SyncTombstone).filter(models.SyncTombstone.id > last_t).count()
    return {{'role': 'server', 'server_id': models.SERVER_ID, 'configured': bool(st.get('last_pull_at')),
            'last_push_at': st.get('last_push_at'), 'last_pull_at': st.get('last_pull_at'), 'waiting': waiting}}
'''.format(MARK=MARK)
    new_main = s
    report.append('main.py: added GET /sync/info, GET /districts, PUT /barangays/{id}/district; registration takes a district')

changed = []
for name, old_s, new_s in [('main.py', main_src, new_main), ('schemas.py', schemas_src, new_schemas)]:
    if new_s != old_s:
        shutil.copy(name, name + '.bak_sync4')
        open(name, 'w').write(new_s)
        changed.append((name, old_s))
r = subprocess.run([sys.executable, '-m', 'py_compile', 'main.py', 'schemas.py'], capture_output=True, text=True)
if r.returncode != 0:
    for name, old_s in changed:
        open(name, 'w').write(old_s)
    print(r.stderr)
    stop('syntax check failed, original files restored')
for line in report:
    print('OK  ' + line)
print('All files compile.' + (' Backups saved as *.bak_sync4' if changed else ''))
