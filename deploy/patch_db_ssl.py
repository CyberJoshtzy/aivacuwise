"""Lets database.py use an encrypted connection when POSTGRES_SSLMODE is set (Aiven requires it).
Without the setting, nothing changes for your local servers. Safe to run twice."""
import shutil
import sys

s = open('database.py').read()
if 'POSTGRES_SSLMODE' in s:
    print('OK  database.py already supports POSTGRES_SSLMODE, skipped')
    sys.exit(0)
a = 'DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"\n'
if s.count(a) != 1:
    sys.exit('STOP: database.py does not have the expected DATABASE_URL line. Nothing was changed.')
s = s.replace(a, a + 'if os.getenv("POSTGRES_SSLMODE"):\n    DATABASE_URL += "?sslmode=" + os.getenv("POSTGRES_SSLMODE")\n')
shutil.copy('database.py', 'database.py.bak_ssl')
open('database.py', 'w').write(s)
print('OK  database.py: uses POSTGRES_SSLMODE when it is set (cloud hub only)')
