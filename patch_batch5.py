"""Batch 5 backend: evacuee photo thumbnails and the Entrance Display data.

Adds:
  POST /evacuees/{id}/photo     save a small face thumbnail (from Pre-Registration's front photo)
  GET  /evacuees/{id}/photo     return it, signed-in accounts only (never public)
  GET  /display/{center_id}     everything the Entrance Display needs in one call
Deleting an evacuee also deletes their photo.

Photos are stored in ~/aivacuwise/data/photos/ (override with the BL_PHOTO_DIR environment
variable). That folder holds personal data: it must stay out of Git (see .gitignore step).

Run from ~/aivacuwise with the venv active:  python3 patch_batch5.py
Safe to run twice.
"""
import re
import shutil
import subprocess
import sys

MARK = '# ---- AiVacuwise: evacuee photos and entrance display (batch 5) ----'
BATCH4 = '# ---- AiVacuwise: pre-registration with webcam photos (batch 4) ----'

src = open('main.py').read()


def stop(msg):
    print('STOP: ' + msg)
    print('Nothing was changed.')
    sys.exit(1)


if MARK in src:
    print('OK  Batch 5 is already in main.py. Nothing to do.')
    sys.exit(0)
if BATCH4 not in src:
    stop('batch 4 not found in main.py. Install batch 4 first.')

s = src
old_del = ("    barangay_id = e.registered_barangay_id\n"
           "    db.delete(e)\n"
           "    db.commit()\n"
           "    await _bl_notify(barangay_id)\n"
           "    return {'deleted': evacuee_id}")
if s.count(old_del) != 1:
    stop('could not find the evacuee delete code from batch 2')
s = s.replace(old_del, old_del.replace("    db.commit()\n", "    db.commit()\n    _bl_remove_photo(evacuee_id)\n"))

getdb = 'get_db' if re.search(r'^from database import .*\bget_db\b', s, re.M) else 'database.get_db'
code = '''

{MARK}
import os as _bl_os
from fastapi.responses import FileResponse as _BLFileResponse


class BLPhoto(_BLBaseModel):
    image: str


def _bl_photo_dir():
    d = _bl_os.environ.get('BL_PHOTO_DIR') or _bl_os.path.join(_bl_os.getcwd(), 'data', 'photos')
    _bl_os.makedirs(d, exist_ok=True)
    return d


def _bl_photo_path(evacuee_id):
    return _bl_os.path.join(_bl_photo_dir(), '%d.jpg' % int(evacuee_id))


def _bl_remove_photo(evacuee_id):
    try:
        _bl_os.remove(_bl_photo_path(evacuee_id))
    except OSError:
        pass


def _bl_short_name(full_name):
    parts = [p for p in (full_name or '').replace(',', ' ').split() if p]
    suffixes = {{'jr', 'jr.', 'sr', 'sr.', 'ii', 'iii', 'iv', 'v'}}
    while len(parts) > 1 and parts[-1].lower() in suffixes:
        parts.pop()
    if not parts:
        return 'Evacuee'
    if len(parts) == 1:
        return parts[0]
    return parts[0] + ' ' + parts[-1][0].upper() + '.'


def _bl_age(birthdate):
    try:
        y, m, d = [int(x) for x in str(birthdate)[:10].split('-')]
        t = _BL3dt.utcnow()
        return t.year - y - ((t.month, t.day) < (m, d))
    except Exception:
        return None


@app.post('/evacuees/{{evacuee_id}}/photo')
def bl_save_photo(evacuee_id: int, payload: BLPhoto, db: _BLSession = _BLDepends({GETDB}),
                  user=_BLDepends(auth.get_current_user)):
    import base64
    import io
    from PIL import Image
    Evacuee = _bl_model('evacuees')
    e = db.query(Evacuee).filter(Evacuee.id == evacuee_id).first()
    if not e:
        raise _BLHTTPException(status_code=404, detail='Evacuee not found.')
    if not _bl_can_edit(user, e.registered_barangay_id):
        raise _BLHTTPException(status_code=403, detail='You can only add photos for your own barangay.')
    try:
        raw = payload.image.split(',', 1)[1] if payload.image.startswith('data:') else payload.image
        img = Image.open(io.BytesIO(base64.b64decode(raw))).convert('RGB')
    except Exception:
        raise _BLHTTPException(status_code=422, detail='The photo could not be read.')
    w, h = img.size
    side = min(w, h)
    img = img.crop(((w - side) // 2, (h - side) // 2, (w - side) // 2 + side, (h - side) // 2 + side)).resize((240, 240))
    img.save(_bl_photo_path(e.id), format='JPEG', quality=80)
    return {{'saved': True, 'evacuee_id': e.id}}


@app.get('/evacuees/{{evacuee_id}}/photo')
def bl_get_photo(evacuee_id: int, db: _BLSession = _BLDepends({GETDB}), user=_BLDepends(auth.get_current_user)):
    Evacuee = _bl_model('evacuees')
    e = db.query(Evacuee).filter(Evacuee.id == evacuee_id).first()
    if not e:
        raise _BLHTTPException(status_code=404, detail='Evacuee not found.')
    if not _bl_can_edit(user, e.registered_barangay_id):
        raise _BLHTTPException(status_code=403, detail='Not allowed.')
    path = _bl_photo_path(e.id)
    if not _bl_os.path.exists(path):
        raise _BLHTTPException(status_code=404, detail='No photo saved for this evacuee.')
    return _BLFileResponse(path, media_type='image/jpeg', headers={{'Cache-Control': 'private, max-age=300'}})


@app.get('/display/{{center_id}}')
def bl_display(center_id: int, db: _BLSession = _BLDepends({GETDB}), user=_BLDepends(auth.get_current_user)):
    Center = _bl_model('evacuation_centers')
    Evacuee = _bl_model('evacuees')
    Checkin = _bl_model('checkin_records')
    Barangay = _bl_model('barangays')
    Incident = _bl_model('incidents')
    c = db.query(Center).filter(Center.id == center_id).first()
    if not c:
        raise _BLHTTPException(status_code=404, detail='Evacuation center not found.')
    if not _bl_can_edit(user, c.barangay_id):
        raise _BLHTTPException(status_code=403, detail='You can only open the display for your own barangay\\'s centers.')
    b = db.query(Barangay).filter(Barangay.id == c.barangay_id).first()
    residents = db.query(Evacuee).filter(Evacuee.registered_barangay_id == c.barangay_id).all()

    def latest(ev_id):
        return db.query(Checkin).filter(Checkin.evacuee_id == ev_id).order_by(Checkin.timestamp.desc(), Checkin.id.desc()).first()

    waiting, safe = [], 0
    for e in residents:
        r = latest(e.id)
        inside = r is not None and r.event_type == 'check_in'
        if inside:
            safe += 1
            continue
        tags = []
        needs = [x for x in (getattr(e, 'special_needs', None) or '').split(',') if x]
        age = _bl_age(e.birthdate)
        if 'Senior citizen' in needs or (age is not None and age >= 60):
            tags.append('Senior')
        if 'PWD' in needs:
            tags.append('PWD')
        if 'Pregnant' in needs:
            tags.append('Pregnant')
        waiting.append({{'id': e.id, 'name': _bl_short_name(e.full_name), 'tags': tags,
                        'has_photo': _bl_os.path.exists(_bl_photo_path(e.id))}})
    waiting.sort(key=lambda w: (0 if w['tags'] else 1, w['name'].lower()))

    arrived = []
    here_ids = set()
    for r in db.query(Checkin).filter(Checkin.evacuation_center_id == c.id, Checkin.event_type == 'check_in').order_by(Checkin.timestamp.desc(), Checkin.id.desc()).limit(200).all():
        if r.evacuee_id in here_ids:
            continue
        cur = latest(r.evacuee_id)
        if cur is None or cur.id != r.id:
            continue
        here_ids.add(r.evacuee_id)
        e = db.query(Evacuee).filter(Evacuee.id == r.evacuee_id).first()
        if e is None:
            continue
        arrived.append({{'id': e.id, 'name': _bl_short_name(e.full_name), 'time': _bl_iso(r.timestamp),
                        'has_photo': _bl_os.path.exists(_bl_photo_path(e.id))}})
        if len(arrived) >= 12:
            break
    inc = db.query(Incident).filter(Incident.barangay_id == c.barangay_id, Incident.ended_at.is_(None)).first()
    return {{
        'center': {{'id': c.id, 'name': c.name, 'capacity': c.capacity}},
        'barangay': b.name if b else None,
        'incident': _bl_incident_dict(inc) if inc else None,
        'expected_total': len(residents), 'safe_total': safe,
        'waiting': waiting, 'arrived': arrived,
    }}
'''.format(MARK=MARK, GETDB=getdb)
s = s.rstrip() + '\n' + code

shutil.copy('main.py', 'main.py.bak_batch5')
open('main.py', 'w').write(s)
r = subprocess.run([sys.executable, '-m', 'py_compile', 'main.py'], capture_output=True, text=True)
if r.returncode != 0:
    open('main.py', 'w').write(src)
    print(r.stderr)
    stop('syntax check failed, main.py restored')
print('OK  main.py: added POST/GET /evacuees/{id}/photo and GET /display/{center_id}')
print('OK  main.py: deleting an evacuee now also deletes their photo')
print('main.py compiles. Backup saved as main.py.bak_batch5')
