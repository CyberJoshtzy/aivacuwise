"""Lets users sign in with email or username. Run from ~/aivacuwise:  python3 patch_email_login.py"""
import re, shutil, subprocess, sys

FILES = ['models.py', 'schemas.py', 'main.py', 'auth.py']
orig = {f: open(f).read() for f in FILES}
new = dict(orig)
report = []

def stop(msg):
    print('STOP: ' + msg)
    print('Nothing was changed.')
    sys.exit(1)

s = new['models.py']
if 'email = Column(' in s:
    report.append('models.py: email column already there, skipped')
else:
    hits = list(re.finditer(r'^([ \t]+)username\s*=\s*Column\(.*$', s, re.M))
    if len(hits) != 1:
        stop('expected 1 username Column line in models.py, found %d' % len(hits))
    m = hits[0]
    s = s[:m.end()] + '\n' + m.group(1) + 'email = Column(String, unique=True, index=True, nullable=True)' + s[m.end():]
    new['models.py'] = s
    report.append('models.py: added email column')

s = new['schemas.py']
if 'email: Optional[str]' in s:
    report.append('schemas.py: email already there, skipped')
else:
    s, n = re.subn(r'^([ \t]+)username:\s*str.*$', lambda m: m.group(0) + '\n' + m.group(1) + 'email: Optional[str] = None', s, flags=re.M)
    if n == 0:
        stop('no "username: str" field found in schemas.py')
    if not re.search(r'^from typing import .*\bOptional\b', s, re.M):
        s = 'from typing import Optional\n' + s
    new['schemas.py'] = s
    report.append('schemas.py: added email to %d schema(s)' % n)

pat = re.compile(r'models\.User\.username\s*==\s*([A-Za-z_][\w.]*)')
done = False
for f, fn in [('main.py', 'def login'), ('auth.py', 'def authenticate_user')]:
    s = new[f]
    i = s.find(fn)
    if i < 0:
        continue
    if 'models.User.email' in s[i:i + 2500]:
        report.append(f + ': login already accepts email, skipped')
        done = True
        break
    m = pat.search(s, i)
    if not m or m.start() - i > 2500:
        continue
    v = m.group(1)
    s = s[:m.start()] + 'or_(models.User.username == %s, models.User.email == %s.strip().lower())' % (v, v) + s[m.end():]
    if not re.search(r'^from sqlalchemy import .*\bor_\b', s, re.M):
        s = 'from sqlalchemy import or_\n' + s
    new[f] = s
    report.append(f + ': login now accepts email or username (in ' + fn + ')')
    done = True
    break
if not done:
    stop('could not find the login query. Run: grep -n "def login" -A 20 main.py')

s = new['main.py']
if 'email=' not in s:
    s, n = re.subn(r'models\.User\(\s*username\s*=\s*([A-Za-z_]\w*)\.username',
                   lambda m: "models.User(email=(%s.email.strip().lower() if getattr(%s, 'email', None) else None), username=%s.username" % (m.group(1), m.group(1), m.group(1)),
                   s)
    new['main.py'] = s
    report.append('main.py: user creation saves email in %d place(s)' % n)

for f in FILES:
    if new[f] != orig[f]:
        shutil.copy(f, f + '.bak_email')
        open(f, 'w').write(new[f])
r = subprocess.run([sys.executable, '-m', 'py_compile'] + FILES, capture_output=True, text=True)
if r.returncode != 0:
    for f in FILES:
        open(f, 'w').write(orig[f])
    print(r.stderr)
    stop('syntax check failed, original files restored')
for line in report:
    print('OK  ' + line)
print('All files compile. Backups saved as *.bak_email')
