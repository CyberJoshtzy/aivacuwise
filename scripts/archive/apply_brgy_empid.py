"""Barangay registration now requires and saves the official's employee ID number."""
s = open('main.py').read()
if 'employee_id: _BLOptional[str] = None\n    evacuation_centers' not in s:
    a = "    evacuation_centers: _BLOptional[list] = None\n"
    assert a in s, 'run apply_register_centers.py first'
    s = s.replace(a, "    employee_id: _BLOptional[str] = None\n" + a, 1)
    a = "    User = models.User\n    Barangay = _bl_model('barangays')"
    assert a in s, 'register code not found'
    s = s.replace(a, """    emp = ' '.join((payload.employee_id or '').split())
    if len(emp) < 3:
        raise _BLHTTPException(status_code=422, detail='Enter your barangay employee ID number.')
""" + a, 1)
    a = "             barangay_id=b.id, full_name=person, designation=designation, mobile_number=digits)"
    assert a in s, 'user creation not found'
    s = s.replace(a, "             barangay_id=b.id, full_name=person, designation=designation, mobile_number=digits, employee_id=emp)", 1)
    open('main.py', 'w').write(s)
    print('main.py: employee ID now required for barangay sign-up')
else:
    print('main.py: already done')
