"""Batch 6 backend: barangay self-registration (the Register Barangay Account screen).

Adds:
  GET  /register/config   public: tells the page whether a registration code is required
  POST /register          public: creates the official's account, and the barangay if it is new
and three new user columns: full_name, designation, mobile_number.

Optional safeguard: put REGISTRATION_CODE=something in .env and restart the service; then only
people given that code by the City DRRMO can register. Without it, registration is open to anyone
on the local network.

Run from ~/ai-vacuwise with the venv active:
  python3 patch_batch6.py
  python3 migrate_batch6.py
Safe to run twice.
"""
import re
import shutil
import subprocess
import sys

MARK = '# ---- Ai-Vacuwise: barangay self-registration (batch 6) ----'
BATCH5 = '# ---- Ai-Vacuwise: evacuee photos and entrance display (batch 5) ----'

models_src = open('models.py').read()
main_src = open('main.py').read()
new_models, new_main = models_src, main_src
report = []


def stop(msg):
    print('STOP: ' + msg)
    print('Nothing was changed.')
    sys.exit(1)


if BATCH5 not in main_src:
    stop('batch 5 not found in main.py. Install batch 5 first.')

if 'designation = Column(' in models_src:
    report.append('models.py: user columns already there, skipped')
else:
    hits = list(re.finditer(r'^([ \t]+)email\s*=\s*Column\(.*$', models_src, re.M))
    if len(hits) != 1:
        stop('expected 1 email column line in models.py, found %d' % len(hits))
    m = hits[0]
    ind = m.group(1)
    new_models = (models_src[:m.end()] +
                  '\n' + ind + 'full_name = Column(String, nullable=True)' +
                  '\n' + ind + 'designation = Column(String, nullable=True)' +
                  '\n' + ind + 'mobile_number = Column(String, nullable=True)' +
                  models_src[m.end():])
    report.append('models.py: added full_name, designation, mobile_number to User')

if MARK in main_src:
    report.append('main.py: batch 6 already there, skipped')
else:
    getdb = 'get_db' if re.search(r'^from database import .*\bget_db\b', main_src, re.M) else 'database.get_db'
    code = '''

{MARK}
import re as _bl_re

BL_DESIGNATIONS = ['Barangay Chairman', 'Barangay Kagawad', 'SK Chairman', 'Barangay Secretary']


class BLRegister(_BLBaseModel):
    barangay_name: str
    designation: str
    designation_other: _BLOptional[str] = None
    full_name: str
    email: str
    mobile_number: str
    password: str
    registration_code: _BLOptional[str] = None


def _bl_required_code():
    return (_bl_os.environ.get('REGISTRATION_CODE') or '').strip()


@app.get('/register/config')
def bl_register_config():
    return {{'code_required': bool(_bl_required_code()), 'designations': BL_DESIGNATIONS}}


@app.post('/register', status_code=201)
async def bl_register(payload: BLRegister, db: _BLSession = _BLDepends({GETDB})):
    code = _bl_required_code()
    if code and (payload.registration_code or '').strip() != code:
        raise _BLHTTPException(status_code=403, detail='The registration code is not correct. Ask the City DRRMO for it.')
    name = ' '.join((payload.barangay_name or '').split())
    person = ' '.join((payload.full_name or '').split())
    email = (payload.email or '').strip().lower()
    if not name:
        raise _BLHTTPException(status_code=422, detail='Enter the barangay name.')
    if not person:
        raise _BLHTTPException(status_code=422, detail='Enter your full name.')
    if not _bl_re.fullmatch(r'[^@\\s]+@[^@\\s]+\\.[^@\\s]+', email):
        raise _BLHTTPException(status_code=422, detail='Enter a valid email address.')
    designation = (payload.designation or '').strip()
    if designation not in BL_DESIGNATIONS:
        designation = ' '.join((payload.designation_other or '').split())
        if not designation:
            raise _BLHTTPException(status_code=422, detail='Choose your designation, or type it under Others.')
    digits = _bl_re.sub(r'\\D', '', payload.mobile_number or '')
    if digits.startswith('63'):
        digits = '0' + digits[2:]
    if len(digits) == 10 and digits.startswith('9'):
        digits = '0' + digits
    if not _bl_re.fullmatch(r'09\\d{{9}}', digits):
        raise _BLHTTPException(status_code=422, detail='Enter a valid Philippine mobile number, such as 0917 123 4567.')
    pw = payload.password or ''
    if len(pw) < 8 or not _bl_re.search(r'[A-Za-z]', pw) or not _bl_re.search(r'\\d', pw):
        raise _BLHTTPException(status_code=422, detail='Use a password with at least 8 characters, including letters and a number.')
    User = models.User
    Barangay = _bl_model('barangays')
    taken = db.query(User).filter(_BL3func.lower(User.email) == email).first() or db.query(User).filter(_BL3func.lower(User.username) == email).first()
    if taken:
        raise _BLHTTPException(status_code=409, detail='An account with this email already exists. Sign in instead.')
    b = db.query(Barangay).filter(_BL3func.lower(Barangay.name) == name.lower()).first()
    created = False
    if b is None:
        b = Barangay(name=name)
        db.add(b)
        db.flush()
        created = True
    u = User(username=email, email=email, password_hash=auth.get_password_hash(pw), role='barangay_official',
             barangay_id=b.id, full_name=person, designation=designation, mobile_number=digits)
    db.add(u)
    db.commit()
    return {{'id': u.id, 'email': email, 'barangay_id': b.id, 'barangay': b.name, 'new_barangay': created}}
'''.format(MARK=MARK, GETDB=getdb)
    new_main = main_src.rstrip() + '\n' + code
    report.append('main.py: added GET /register/config and POST /register')

changed = []
for fname, old, new in [('models.py', models_src, new_models), ('main.py', main_src, new_main)]:
    if new != old:
        shutil.copy(fname, fname + '.bak_batch6')
        open(fname, 'w').write(new)
        changed.append((fname, old))
r = subprocess.run([sys.executable, '-m', 'py_compile', 'models.py', 'main.py'], capture_output=True, text=True)
if r.returncode != 0:
    for fname, old in changed:
        open(fname, 'w').write(old)
    print(r.stderr)
    stop('syntax check failed, original files restored')
for line in report:
    print('OK  ' + line)
print('All files compile.' + (' Backups saved as *.bak_batch6' if changed else ''))
