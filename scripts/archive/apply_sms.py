"""Adds the GSM SMS Alert Sender router to main.py and the two settings to .env (run from ~/bilislikas2.0)."""
import secrets

s = open('main.py').read()
if 'import sms' not in s:
    s += '\nimport sms\napp.include_router(sms.router)\n'
    open('main.py', 'w').write(s)
    print('main.py: SMS router added')
else:
    print('main.py: SMS router already there')

env = open('.env').read() if __import__('os').path.exists('.env') else ''
add = ''
if 'SMS_ENABLED' not in env:
    add += '\nSMS_ENABLED=1'
if 'SMS_DEVICE_KEY' not in env:
    add += '\nSMS_DEVICE_KEY=' + secrets.token_hex(16)
if add:
    open('.env', 'a').write(add + '\n')
    print('.env: SMS_ENABLED and SMS_DEVICE_KEY added (do not paste the key in chat)')
print('Done. Restart: sudo systemctl restart bilislikas')
