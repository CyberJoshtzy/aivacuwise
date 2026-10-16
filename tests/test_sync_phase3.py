"""Tests for cloud sync phase 3: push, pull, last-write-wins, deletions, linking duplicates, and keys."""

import uuid as uuidlib
from datetime import datetime, timedelta

import pytest

import models
import sync_core
from database import get_db
from main import app

KEY = "test-sync-key"


@pytest.fixture(autouse=True)
def sync_key(monkeypatch):
    monkeypatch.setenv("SYNC_KEY", KEY)


def _db():
    return next(app.dependency_overrides.get(get_db, get_db)())


def _id(obj):
    return obj["id"] if isinstance(obj, dict) else obj.id


def _u():
    return str(uuidlib.uuid4())


def _t(minutes=0):
    return (datetime.utcnow() + timedelta(minutes=minutes)).isoformat()


def _remote_bundle(origin="server-z"):
    b, c, e, ck = _u(), _u(), _u(), _u()
    rows = [
        {
            "table": "checkin_records",
            "uuid": ck,
            "data": {
                "evacuee_id": e,
                "evacuation_center_id": c,
                "event_type": "check_in",
                "timestamp": _t(),
                "updated_at": _t(),
                "origin": origin,
            },
        },
        {
            "table": "evacuees",
            "uuid": e,
            "data": {
                "full_name": "Remote Resident",
                "sex": "Female",
                "registered_barangay_id": b,
                "identification_method": "facial_recognition",
                "facial_embedding": "[0.1, 0.2]",
                "updated_at": _t(),
                "origin": origin,
            },
        },
        {
            "table": "evacuation_centers",
            "uuid": c,
            "data": {
                "name": "Remote Gym",
                "capacity": 50,
                "barangay_id": b,
                "updated_at": _t(),
                "origin": origin,
            },
        },
        {
            "table": "barangays",
            "uuid": b,
            "data": {"name": "Barangay 999", "updated_at": _t(), "origin": origin},
        },
    ]
    return rows, {"barangay": b, "center": c, "evacuee": e, "checkin": ck}


def _push(client, rows, tombstones=(), origin="server-z", key=KEY):
    return client.post(
        "/sync/push",
        json={"server_id": origin, "rows": rows, "tombstones": list(tombstones)},
        headers={"X-Sync-Key": key},
    )


def test_push_requires_the_key(client):
    assert _push(client, [], key="wrong").status_code == 401


def test_push_without_configured_key(client, monkeypatch):
    monkeypatch.delenv("SYNC_KEY")
    assert _push(client, []).status_code == 503


def test_push_applies_records_in_dependency_order(client):
    rows, ids = _remote_bundle()  # deliberately sent children first
    r = _push(client, rows)
    assert r.status_code == 200, r.text
    assert set(r.json()["applied"]) == set(ids.values())
    db = _db()
    ev = db.query(models.Evacuee).filter_by(uuid=ids["evacuee"]).first()
    br = db.query(models.Barangay).filter_by(uuid=ids["barangay"]).first()
    ck = db.query(models.CheckinRecord).filter_by(uuid=ids["checkin"]).first()
    assert ev.registered_barangay_id == br.id and ck.evacuee_id == ev.id
    assert ev.origin == "server-z" and ev.sync_dirty is False  # imported data is not sent back out


def test_pull_excludes_the_requesting_server(client):
    rows, ids = _remote_bundle()
    _push(client, rows)
    own = client.get(
        "/sync/pull", params={"exclude_origin": "server-z"}, headers={"X-Sync-Key": KEY}
    ).json()
    other = client.get(
        "/sync/pull", params={"exclude_origin": "server-a"}, headers={"X-Sync-Key": KEY}
    ).json()
    assert own["rows"] == []
    got = {r["uuid"]: r for r in other["rows"]}
    assert set(got) == set(ids.values())
    assert (
        got[ids["evacuee"]]["data"]["registered_barangay_id"] == ids["barangay"]
    )  # sent as uuid, not local id
    again = client.get(
        "/sync/pull",
        params={"since": other["next"], "exclude_origin": "server-a"},
        headers={"X-Sync-Key": KEY},
    ).json()
    assert again["rows"] == []


def test_last_write_wins(client):
    rows, ids = _remote_bundle()
    _push(client, rows)
    ev = [r for r in rows if r["table"] == "evacuees"][0]
    older = {
        "table": "evacuees",
        "uuid": ids["evacuee"],
        "data": dict(ev["data"], full_name="Old Name", updated_at=_t(-60)),
    }
    newer = {
        "table": "evacuees",
        "uuid": ids["evacuee"],
        "data": dict(ev["data"], full_name="New Name", updated_at=_t(60)),
    }
    assert ids["evacuee"] in _push(client, [older]).json()["skipped"]
    assert ids["evacuee"] in _push(client, [newer]).json()["applied"]
    db = _db()
    db.expire_all()
    assert db.query(models.Evacuee).filter_by(uuid=ids["evacuee"]).first().full_name == "New Name"


def test_tombstone_removes_evacuee_and_its_checkins(client):
    rows, ids = _remote_bundle()
    _push(client, rows)
    r = _push(client, [], tombstones=[{"table": "evacuees", "uuid": ids["evacuee"]}])
    assert ids["evacuee"] in r.json()["removed"]
    db = _db()
    db.expire_all()
    assert db.query(models.Evacuee).filter_by(uuid=ids["evacuee"]).first() is None
    assert db.query(models.CheckinRecord).filter_by(uuid=ids["checkin"]).first() is None
    pulled = client.get(
        "/sync/pull", params={"exclude_origin": "server-a"}, headers={"X-Sync-Key": KEY}
    ).json()
    assert {"table": "evacuees", "uuid": ids["evacuee"]} in pulled["tombstones"]


def test_child_without_parent_waits(client):
    lonely = {
        "table": "checkin_records",
        "uuid": _u(),
        "data": {
            "evacuee_id": _u(),
            "evacuation_center_id": _u(),
            "event_type": "check_in",
            "updated_at": _t(),
            "origin": "server-z",
        },
    }
    assert lonely["uuid"] in _push(client, [lonely]).json()["waiting"]


def test_same_barangay_on_two_servers_is_linked_not_duplicated(client, barangay):
    name = barangay["name"] if isinstance(barangay, dict) else barangay.name
    twin = {
        "table": "barangays",
        "uuid": _u(),
        "data": {"name": name, "updated_at": _t(), "origin": "server-z"},
    }
    assert twin["uuid"] in _push(client, [twin]).json()["aliased"]
    db = _db()
    assert db.query(models.Barangay).filter_by(name=name).count() == 1


def test_local_changes_are_marked_until_sent(client, admin_headers, evacuee):
    db = _db()
    row = db.query(models.Evacuee).get(_id(evacuee))
    assert row.sync_dirty is True
    pending = sync_core.dirty_rows(db)
    assert row.uuid in {r["uuid"] for r in pending}
    sync_core.mark_clean(db, [r for r in pending if r["uuid"] == row.uuid])
    db.commit()
    db.expire_all()
    assert db.query(models.Evacuee).get(_id(evacuee)).sync_dirty is False
