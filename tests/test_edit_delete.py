"""Tests for the edit and delete endpoints added by patch_edit_delete.py."""


def _id(obj):
    return obj["id"] if isinstance(obj, dict) else obj.id


def _check_in(client, headers, evacuee_id, center_id):
    r = client.post(
        "/checkin",
        json={
            "evacuee_id": evacuee_id,
            "evacuation_center_id": center_id,
            "event_type": "check_in",
        },
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text


def test_edit_requires_login(client, evacuee):
    client.headers.pop("Authorization", None)  # this test checks the not-signed-in case
    r = client.put("/evacuees/%d" % _id(evacuee), json={"address": "Somewhere"})
    assert r.status_code == 401


def test_edit_evacuee(client, admin_headers, evacuee):
    r = client.put(
        "/evacuees/%d" % _id(evacuee),
        json={"address": "  12 Mabini Street  ", "birthdate": "1950-05-01"},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["address"] == "12 Mabini Street"
    assert str(body["birthdate"]).startswith("1950-05-01")


def test_edit_evacuee_rejects_empty_name(client, admin_headers, evacuee):
    r = client.put("/evacuees/%d" % _id(evacuee), json={"full_name": "   "}, headers=admin_headers)
    assert r.status_code == 422


def test_delete_evacuee_removes_history(client, admin_headers, evacuee, center):
    eid = _id(evacuee)
    _check_in(client, admin_headers, eid, _id(center))
    r = client.delete("/evacuees/%d" % eid, headers=admin_headers)
    assert r.status_code == 200, r.text
    ids = [e["id"] for e in client.get("/evacuees", headers=admin_headers).json()]
    assert eid not in ids


def test_edit_center_capacity_below_occupancy_refused(client, admin_headers, evacuee, center):
    _check_in(client, admin_headers, _id(evacuee), _id(center))
    r = client.put(
        "/evacuation_centers/%d" % _id(center), json={"capacity": 0}, headers=admin_headers
    )
    assert r.status_code == 422
    r = client.put(
        "/evacuation_centers/%d" % _id(center),
        json={"name": "Renamed Center", "capacity": 150},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Renamed Center"


def test_delete_center_with_evacuees_refused(client, admin_headers, evacuee, center):
    _check_in(client, admin_headers, _id(evacuee), _id(center))
    r = client.delete("/evacuation_centers/%d" % _id(center), headers=admin_headers)
    assert r.status_code == 409


def test_delete_unused_center(client, admin_headers, second_center):
    r = client.delete("/evacuation_centers/%d" % _id(second_center), headers=admin_headers)
    assert r.status_code == 200, r.text
