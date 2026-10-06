"""Tests for cloud sync phase 1: every record gets a uuid, updated_at and origin automatically,
deletions leave a tombstone, and evacuees now report their household."""
import time

import models
from database import get_db
from main import app


def _db():
    gen = app.dependency_overrides.get(get_db, get_db)()
    return next(gen)


def _id(obj):
    return obj['id'] if isinstance(obj, dict) else obj.id


def test_new_records_are_stamped(client, admin_headers, evacuee, center, barangay):
    db = _db()
    for cls, rid in [(models.Evacuee, _id(evacuee)), (models.EvacuationCenter, _id(center)), (models.Barangay, _id(barangay))]:
        row = db.query(cls).get(rid)
        assert row.uuid and len(row.uuid) == 36
        assert row.updated_at is not None
        assert row.origin


def test_uuids_are_unique(client, admin_headers, evacuee, center):
    db = _db()
    uuids = [r.uuid for cls in models.SYNCED_MODELS for r in db.query(cls).all()]
    assert len(uuids) == len(set(uuids))


def test_update_moves_updated_at_forward(client, admin_headers, evacuee):
    db = _db()
    eid = _id(evacuee)
    before = db.query(models.Evacuee).get(eid).updated_at
    time.sleep(0.02)
    r = client.put('/evacuees/%d' % eid, json={'address': '9 Rizal Avenue'}, headers=admin_headers)
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.query(models.Evacuee).get(eid).updated_at > before


def test_delete_leaves_tombstone(client, admin_headers, evacuee):
    db = _db()
    eid = _id(evacuee)
    uid = db.query(models.Evacuee).get(eid).uuid
    assert client.delete('/evacuees/%d' % eid, headers=admin_headers).status_code == 200
    db.expire_all()
    t = db.query(models.SyncTombstone).filter_by(record_uuid=uid).first()
    assert t is not None and t.table_name == 'evacuees'


def test_checkin_events_are_stamped(client, admin_headers, evacuee, center):
    r = client.post('/checkin', json={'evacuee_id': _id(evacuee), 'evacuation_center_id': _id(center), 'event_type': 'check_in'}, headers=admin_headers)
    assert r.status_code in (200, 201), r.text
    db = _db()
    rec = db.query(models.CheckinRecord).get(r.json()['id'])
    assert rec.uuid and rec.updated_at and rec.origin


def test_evacuees_list_includes_household(client, admin_headers, barangay):
    body = {'registered_barangay_id': _id(barangay), 'members': [
        {'full_name': 'Pedro Garcia', 'sex': 'Male', 'address': '5 Lakandula St', 'is_head_of_family': True},
        {'full_name': 'Luz Garcia', 'sex': 'Female', 'address': '5 Lakandula St'}]}
    h = client.post('/households', json=body, headers=admin_headers)
    assert h.status_code == 200, h.text
    hid = h.json()['id']
    rows = {e['full_name']: e for e in client.get('/evacuees', headers=admin_headers).json()}
    assert rows['Pedro Garcia']['household_id'] == hid and rows['Pedro Garcia']['is_head_of_family'] is True
    assert rows['Luz Garcia']['household_id'] == hid


def test_sync_status(client, admin_headers, evacuee):
    r = client.get('/sync/status', headers=admin_headers)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d['server_id'] and d['tables']['evacuees']['records'] >= 1
    assert all(t['missing_uuid'] == 0 for t in d['tables'].values())
