"""Adds the City Hall account columns to models.py and the approval check and router to main.py."""
m = open('models.py').read()
if 'account_status' not in m:
    anchor = '    barangay_id = Column(Integer, ForeignKey("barangays.id"), nullable=True)\n'
    i = m.index('class User(Base)')
    j = m.index(anchor, i) + len(anchor)
    m = m[:j] + ('    position = Column(String, nullable=True)\n    office = Column(String, nullable=True)\n'
                 '    employee_id = Column(String, nullable=True)\n    account_status = Column(String, nullable=True, default="active")\n'
                 '    is_superuser = Column(Boolean, nullable=True, default=False)\n') + m[j:]
    open('models.py', 'w').write(m)
    print('models.py updated')
s = open('main.py').read()
if 'waiting for approval' not in s:
    a = '        raise HTTPException(status_code=401, detail="Incorrect username or password")\n    access_token'
    assert a in s, 'login anchor not found'
    s = s.replace(a, a.replace('    access_token', '') + '''    status = getattr(user, "account_status", None) or "active"
    if status == "pending":
        raise HTTPException(status_code=403, detail="Your account is waiting for approval by the City System Administrator.")
    if status in ("rejected", "disabled"):
        raise HTTPException(status_code=403, detail="This account is not active. Contact the City System Administrator.")
    access_token''', 1)
if 'import admin_auth' not in s:
    s += '\nimport admin_auth\napp.include_router(admin_auth.router)\n'
open('main.py', 'w').write(s)
print('main.py updated')
