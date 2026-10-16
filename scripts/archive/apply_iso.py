"""Adds the ISO/IEC 25010 quality safeguards to main.py and auth.py (run from ~/bilislikas2.0). Safe to run twice."""
m = open('main.py').read()
if 'iso_quality.install(app)' not in m:
    m += "\n\n# ISO/IEC 25010 quality safeguards (security, accountability, reliability, performance)\nimport iso_quality\niso_quality.install(app)\n"
    open('main.py', 'w').write(m); print('main.py: quality safeguards added')
else:
    print('main.py: already added')
a = open('auth.py').read()
old = """    if user is None:
        raise credentials_exception
    return user
"""
new = """    if user is None:
        raise credentials_exception
    # ISO/IEC 25010 Security: a disabled, rejected or pending account loses access right away
    if (getattr(user, "account_status", None) or "active") != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="This account is not active. Contact the City Hall IT Administrator.")
    return user
"""
if 'account loses access' in a:
    print('auth.py: already updated')
elif old in a:
    open('auth.py', 'w').write(a.replace(old, new, 1)); print('auth.py: account status check added')
else:
    print('auth.py: could not find the place to edit. Send auth.py to Claude.')
