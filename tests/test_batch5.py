"""Tests for evacuee photos and the entrance display endpoint."""
import base64
import io

import pytest


@pytest.fixture(autouse=True)
def photo_dir(tmp_path, monkeypatch):
    # Keep test photos out of the real data/photos folder.
    monkeypatch.setenv('BL_PHOTO_DIR', str(tmp_path))


def _id(obj):
    return obj['id'] if isinstance(obj, dict) else obj.id


def _jpeg():
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (640, 480), (120, 160, 200)).save(buf, format='JPEG')
    return 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()


def test_photo_requires_login(client, evacuee):
    assert client.get('/evacuees/%d/photo' % _id(evacuee)).status_code == 401


def test_save_and_get_photo(client, admin_headers, evacuee):
    eid = _id(evacuee)
    assert client.get('/evacuees/%d/photo' % eid, headers=admin_headers).status_code == 404
    r = client.post('/evacuees/%d/photo' % eid, json={'image': _jpeg()}, headers=admin_headers)
    assert r.status_code == 200, r.text
    r = client.get('/evacuees/%d/photo' % eid, headers=admin_headers)
    assert r.status_code == 200
    assert r.headers['content-type'] == 'image/jpeg'
    from PIL import Image
    assert Image.open(io.BytesIO(r.content)).size == (240, 240)


def test_bad_photo_rejected(client, admin_headers, evacuee):
    r = client.post('/evacuees/%d/photo' % _id(evacuee), json={'image': 'not-a-photo'}, headers=admin_headers)
    assert r.status_code == 422


def test_display_lists_waiting_then_arrived(client, admin_headers, evacuee, center):
    eid, cid = _id(evacuee), _id(center)
    client.post('/evacuees/%d/photo' % eid, json={'image': _jpeg()}, headers=admin_headers)
    d = client.get('/display/%d' % cid, headers=admin_headers).json()
    w = [x for x in d['waiting'] if x['id'] == eid]
    assert w and w[0]['has_photo'] is True
    r = client.post('/checkin', json={'evacuee_id': eid, 'evacuation_center_id': cid, 'event_type': 'check_in'}, headers=admin_headers)
    assert r.status_code in (200, 201), r.text
    d = client.get('/display/%d' % cid, headers=admin_headers).json()
    assert eid not in [x['id'] for x in d['waiting']]
    assert eid in [x['id'] for x in d['arrived']]
    assert d['safe_total'] >= 1


def test_delete_evacuee_removes_photo(client, admin_headers, evacuee, tmp_path):
    eid = _id(evacuee)
    client.post('/evacuees/%d/photo' % eid, json={'image': _jpeg()}, headers=admin_headers)
    assert (tmp_path / ('%d.jpg' % eid)).exists()
    assert client.delete('/evacuees/%d' % eid, headers=admin_headers).status_code == 200
    assert not (tmp_path / ('%d.jpg' % eid)).exists()
