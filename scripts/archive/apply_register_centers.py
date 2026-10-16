"""Barangay registration also creates its evacuation centers."""
s = open('main.py').read()
if 'evacuation_centers: _BLOptional[list] = None' not in s:
    a = "    district: _BLOptional[str] = None\n\n\ndef _bl_required_code():"
    assert a in s, 'BLRegister not found'
    s = s.replace(a, "    district: _BLOptional[str] = None\n    evacuation_centers: _BLOptional[list] = None\n\n\ndef _bl_required_code():", 1)
    a = """    db.add(u)
    db.commit()
    return {'id': u.id, 'email': email, 'barangay_id': b.id, 'barangay': b.name, 'new_barangay': created}"""
    assert a in s, 'register save not found'
    s = s.replace(a, """    db.add(u)
    Center = _bl_model('evacuation_centers')
    added = 0
    for c in (payload.evacuation_centers or []):
        try:
            cname = ' '.join(str(c.get('name') or '').split())
            caddr = ' '.join(str(c.get('address') or '').split())
            ccap = int(c.get('capacity') or 0)
        except (AttributeError, TypeError, ValueError):
            continue
        if not cname or not caddr or ccap <= 0:
            raise _BLHTTPException(status_code=422, detail='Each evacuation center needs a name, an address and a capacity.')
        if db.query(Center).filter(Center.barangay_id == b.id, _BL3func.lower(Center.name) == cname.lower()).first():
            continue
        db.add(Center(name=cname, address=caddr, capacity=ccap, barangay_id=b.id))
        added += 1
    db.commit()
    return {'id': u.id, 'email': email, 'barangay_id': b.id, 'barangay': b.name, 'new_barangay': created, 'centers_added': added}""", 1)
    open('main.py', 'w').write(s)
    print('main.py: registration now saves evacuation centers')
else:
    print('main.py: already done')
