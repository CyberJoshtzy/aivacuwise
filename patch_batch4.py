"""Batch 4 backend: pre-registration with webcam photos.

Adds:
  POST /faces/encode             3 photos (base64) -> checks each photo, returns one averaged 128-number face signature
  POST /households/{id}/members  add a person to an existing household
  GET  /evacuee_details          civil status, special needs, emergency contact for each evacuee
  and lets PUT /evacuees/{id} also update civil_status, special_needs, emergency_contact.

Run from ~/aivacuwise with the venv active:
  python3 patch_batch4.py
  python3 migrate_batch4.py
Safe to run twice.
"""
import re
import shutil
import subprocess
import sys

MARK = '# ---- AiVacuwise: pre-registration with webcam photos (batch 4) ----'
BATCH2 = '# ---- AiVacuwise: edit and delete endpoints (batch 2) ----'

models_src = open('models.py').read()
main_src = open('main.py').read()
new_models, new_main = models_src, main_src
report = []


def stop(msg):
    print('STOP: ' + msg)
    print('Nothing was changed.')
    sys.exit(1)


if BATCH2 not in main_src:
    stop('batch 2 endpoints not found in main.py.')

# ---------- models.py: three new optional columns on Evacuee ----------
if 'special_needs = Column(' in models_src:
    report.append('models.py: new evacuee columns already there, skipped')
else:
    hits = list(re.finditer(r'^([ \t]+)identification_method\s*=\s*Column\(.*$', models_src, re.M))
    if len(hits) != 1:
        stop('expected 1 identification_method column line in models.py, found %d' % len(hits))
    m = hits[0]
    ind = m.group(1)
    add = ('\n' + ind + 'civil_status = Column(String, nullable=True)'
           '\n' + ind + 'special_needs = Column(String, nullable=True)'
           '\n' + ind + 'emergency_contact = Column(String, nullable=True)')
    new_models = models_src[:m.end()] + add + models_src[m.end():]
    report.append('models.py: added civil_status, special_needs, emergency_contact to Evacuee')

# ---------- main.py: extend the batch 2 update schema and output ----------
if MARK in main_src:
    report.append('main.py: batch 4 already there, skipped')
else:
    s = new_main
    old_cls = "    contact_number: _BLOptional[str] = None\n\n\nclass BLCenterUpdate(_BLBaseModel):"
    if s.count(old_cls) != 1:
        stop('could not find BLEvacueeUpdate in the batch 2 block')
    s = s.replace(old_cls, "    contact_number: _BLOptional[str] = None\n"
                           "    civil_status: _BLOptional[str] = None\n"
                           "    special_needs: _BLOptional[list] = None\n"
                           "    emergency_contact: _BLOptional[str] = None\n\n\nclass BLCenterUpdate(_BLBaseModel):")
    old_loop = "        if isinstance(value, str):\n            value = value.strip()\n        setattr(e, key, value)"
    if s.count(old_loop) != 1:
        stop('could not find the evacuee update loop in the batch 2 block')
    s = s.replace(old_loop, "        if key == 'special_needs':\n"
                            "            value = ','.join(sorted({str(x).strip() for x in (value or []) if str(x).strip()})) or None\n"
                            "        if isinstance(value, str):\n            value = value.strip()\n        setattr(e, key, value)")
    old_dict = "'household_id': e.household_id, 'is_head_of_family': e.is_head_of_family,"
    if s.count(old_dict) != 1:
        stop('could not find the evacuee output dictionary in the batch 2 block')
    s = s.replace(old_dict, old_dict + "\n        'civil_status': getattr(e, 'civil_status', None),"
                                       "\n        'special_needs': [x for x in (getattr(e, 'special_needs', None) or '').split(',') if x],"
                                       "\n        'emergency_contact': getattr(e, 'emergency_contact', None),")
    getdb = 'get_db' if re.search(r'^from database import .*\bget_db\b', s, re.M) else 'database.get_db'
    code = '''

{MARK}
class BLFaceImages(_BLBaseModel):
    images: list
    angles: _BLOptional[list] = None


class BLMemberCreate(_BLBaseModel):
    full_name: str
    birthdate: _BLDate
    sex: str
    address: str
    contact_number: _BLOptional[str] = None
    civil_status: _BLOptional[str] = None
    special_needs: _BLOptional[list] = None
    emergency_contact: _BLOptional[str] = None


@app.post('/faces/encode')
def bl_faces_encode(payload: BLFaceImages, user=_BLDepends(auth.get_current_user)):
    """Checks each photo for exactly one face and returns their averaged face signature.
    Plain def (not async), so FastAPI runs the slow face math in a worker thread."""
    import base64
    import io
    import numpy as np
    from PIL import Image
    try:
        import face_recognition
    except ImportError:
        raise _BLHTTPException(status_code=503, detail='Face recognition is not installed on the server.')
    images = payload.images or []
    if not 1 <= len(images) <= 5:
        raise _BLHTTPException(status_code=422, detail='Send between 1 and 5 photos.')
    angles = payload.angles or []
    photos, encodings = [], []
    for idx, data in enumerate(images):
        label = str(angles[idx]) if idx < len(angles) else 'photo %d' % (idx + 1)
        try:
            raw = data.split(',', 1)[1] if str(data).startswith('data:') else data
            img = Image.open(io.BytesIO(base64.b64decode(raw))).convert('RGB')
        except Exception:
            photos.append({{'angle': label, 'ok': False, 'message': 'The ' + label + ' photo could not be read. Retake it.'}})
            continue
        arr = np.array(img)
        locs = face_recognition.face_locations(arr, number_of_times_to_upsample=1, model='hog')
        if not locs:
            photos.append({{'angle': label, 'ok': False, 'message': 'No face found in the ' + label + ' photo. Face the light, remove caps or sunglasses, and turn the head a little less.'}})
            continue
        if len(locs) > 1:
            photos.append({{'angle': label, 'ok': False, 'message': 'More than one face in the ' + label + ' photo. Only the evacuee should be in view.'}})
            continue
        encodings.append(face_recognition.face_encodings(arr, known_face_locations=locs, num_jitters=1)[0])
        photos.append({{'angle': label, 'ok': True, 'message': 'Face found in the ' + label + ' photo.'}})
    ok = len(encodings) == len(images)
    worst = 0.0
    if ok and len(encodings) > 1:
        worst = max(float(np.linalg.norm(a - b)) for i, a in enumerate(encodings) for b in encodings[i + 1:])
        if worst > 0.6:
            ok = False
            photos.append({{'angle': 'all', 'ok': False, 'message': 'The photos do not look like the same person. Retake all three.'}})
    return {{
        'ok': ok, 'photos': photos, 'max_distance': round(worst, 3),
        'embedding': [float(x) for x in np.mean(encodings, axis=0)] if ok else None,
    }}


@app.post('/households/{{household_id}}/members')
async def bl_add_member(household_id: int, payload: BLMemberCreate, db: _BLSession = _BLDepends({GETDB}),
                        user=_BLDepends(auth.get_current_user)):
    Household = _bl_model('households')
    Evacuee = _bl_model('evacuees')
    h = db.query(Household).filter(Household.id == household_id).first()
    if not h:
        raise _BLHTTPException(status_code=404, detail='Household not found.')
    if not _bl_can_edit(user, h.registered_barangay_id):
        raise _BLHTTPException(status_code=403, detail='You can only add members to your own barangay\\'s households.')
    if not payload.full_name.strip() or not payload.address.strip() or not payload.sex.strip():
        raise _BLHTTPException(status_code=422, detail='Full name, sex, and address are required.')
    birth = payload.birthdate
    if isinstance(Evacuee.birthdate.property.columns[0].type, _BLString):
        birth = birth.isoformat()
    needs = ','.join(sorted({{str(x).strip() for x in (payload.special_needs or []) if str(x).strip()}})) or None
    e = Evacuee(full_name=payload.full_name.strip(), birthdate=birth, sex=payload.sex.strip(), address=payload.address.strip(),
                contact_number=(payload.contact_number or '').strip() or None, registered_barangay_id=h.registered_barangay_id,
                household_id=h.id, is_head_of_family=False, identification_method='facial_recognition',
                civil_status=payload.civil_status, special_needs=needs, emergency_contact=payload.emergency_contact)
    db.add(e)
    db.commit()
    db.refresh(e)
    await _bl_notify(h.registered_barangay_id)
    return _bl_evacuee_dict(e)


@app.get('/evacuee_details')
def bl_evacuee_details(db: _BLSession = _BLDepends({GETDB}), user=_BLDepends(auth.get_current_user)):
    Evacuee = _bl_model('evacuees')
    q = db.query(Evacuee)
    if user.role != 'city_admin':
        q = q.filter(Evacuee.registered_barangay_id == user.barangay_id)
    return [{{
        'id': e.id, 'civil_status': e.civil_status, 'emergency_contact': e.emergency_contact,
        'special_needs': [x for x in (e.special_needs or '').split(',') if x],
    }} for e in q.all()]
'''.format(MARK=MARK, GETDB=getdb)
    new_main = s.rstrip() + '\n' + code
    report.append('main.py: added POST /faces/encode, POST /households/{id}/members, GET /evacuee_details; PUT /evacuees/{id} accepts the new fields')

changed = []
for name, old, new in [('models.py', models_src, new_models), ('main.py', main_src, new_main)]:
    if new != old:
        shutil.copy(name, name + '.bak_batch4')
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
print('All files compile.' + (' Backups saved as *.bak_batch4' if changed else ''))
