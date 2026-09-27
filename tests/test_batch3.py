"""Tests for incidents (start/end evacuation) and barangay edit/delete."""


def _id(obj):
    return obj['id'] if isinstance(obj, dict) else obj.id


def _start(client, headers, barangay, kind='Fire'):
    return client.post('/incidents', json={'disaster_type': kind, 'barangay_id': _id(barangay)}, headers=headers)


def test_start_and_end_incident(client, admin_headers, barangay):
    r = _start(client, admin_headers, barangay)
    assert r.status_code == 200, r.text
    inc = r.json()
    assert inc['active'] is True and inc['disaster_type'] == 'Fire'
    r = client.post('/incidents/%d/end' % inc['id'], headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()['active'] is False


def test_only_one_active_incident_per_barangay(client, admin_headers, barangay):
    assert _start(client, admin_headers, barangay).status_code == 200
    assert _start(client, admin_headers, barangay, 'Flood').status_code == 409


def test_unknown_disaster_type_rejected(client, admin_headers, barangay):
    assert _start(client, admin_headers, barangay, 'Zombies').status_code == 422


def test_list_active_incidents(client, admin_headers, barangay):
    _start(client, admin_headers, barangay, 'earthquake')
    r = client.get('/incidents?active=true', headers=admin_headers)
    assert r.status_code == 200
    assert [i['disaster_type'] for i in r.json()] == ['Earthquake']


def test_incidents_require_login(client):
    assert client.get('/incidents').status_code == 401


def test_edit_barangay_name(client, admin_headers, barangay):
    r = client.put('/barangays/%d' % _id(barangay), json={'name': '  Barangay 200  '}, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()['name'] == 'Barangay 200'


def test_official_cannot_delete_barangay(client, staff_headers, barangay):
    assert client.delete('/barangays/%d' % _id(barangay), headers=staff_headers).status_code == 403


def test_delete_barangay_with_center_refused(client, admin_headers, barangay, center):
    r = client.delete('/barangays/%d' % _id(barangay), headers=admin_headers)
    assert r.status_code == 409
    assert 'evacuation centers' in r.json()['detail']


def test_delete_empty_barangay(client, admin_headers):
    r = client.post('/barangays', json={'name': 'Empty Barangay'}, headers=admin_headers)
    assert r.status_code in (200, 201), r.text
    r = client.delete('/barangays/%d' % r.json()['id'], headers=admin_headers)
    assert r.status_code == 200, r.text
