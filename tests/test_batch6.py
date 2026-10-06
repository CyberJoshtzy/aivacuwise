"""Tests for barangay self-registration."""
import pytest


@pytest.fixture(autouse=True)
def no_code(monkeypatch):
    monkeypatch.delenv('REGISTRATION_CODE', raising=False)


def _body(**over):
    b = {'barangay_name': 'Barangay 777, Zone 70', 'designation': 'Barangay Chairman', 'full_name': 'Rosa Magbanua',
         'email': 'Rosa.Magbanua@brgy777.gov.ph', 'mobile_number': '+63 917 123 4567', 'password': 'Evacuate2026'}
    b.update(over)
    return b


def test_register_new_barangay_then_sign_in(client):
    r = client.post('/register', json=_body())
    assert r.status_code == 201, r.text
    d = r.json()
    assert d['new_barangay'] is True and d['email'] == 'rosa.magbanua@brgy777.gov.ph'
    r = client.post('/login', data={'username': 'rosa.magbanua@brgy777.gov.ph', 'password': 'Evacuate2026'})
    assert r.status_code == 200, r.text
    me = client.get('/users/me', headers={'Authorization': 'Bearer ' + r.json()['access_token']}).json()
    assert me['role'] == 'barangay_official' and me['barangay_id'] == d['barangay_id']


def test_duplicate_email_refused(client):
    assert client.post('/register', json=_body()).status_code == 201
    assert client.post('/register', json=_body(barangay_name='Another Barangay')).status_code == 409


def test_existing_barangay_is_joined(client, barangay):
    name = (barangay['name'] if isinstance(barangay, dict) else barangay.name).upper()
    r = client.post('/register', json=_body(barangay_name='  ' + name + ' ', email='kagawad@example.com', designation='Barangay Kagawad'))
    assert r.status_code == 201, r.text
    assert r.json()['new_barangay'] is False


def test_other_designation(client):
    r = client.post('/register', json=_body(designation='other', designation_other='BDRRM Officer'))
    assert r.status_code == 201, r.text
    r = client.post('/register', json=_body(email='x@example.com', designation='other', designation_other=''))
    assert r.status_code == 422


@pytest.mark.parametrize('field,value', [('password', 'short1'), ('password', 'onlyletters'), ('mobile_number', '12345'),
                                         ('email', 'not-an-email'), ('barangay_name', '   ')])
def test_bad_input_rejected(client, field, value):
    assert client.post('/register', json=_body(**{field: value})).status_code == 422


def test_registration_code_when_configured(client, monkeypatch):
    monkeypatch.setenv('REGISTRATION_CODE', 'DRRMO-2026')
    assert client.get('/register/config').json()['code_required'] is True
    assert client.post('/register', json=_body()).status_code == 403
    assert client.post('/register', json=_body(registration_code='DRRMO-2026')).status_code == 201
