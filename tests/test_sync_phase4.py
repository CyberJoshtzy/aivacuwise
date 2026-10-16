"""Tests for cloud sync phase 4: sync info for the sidebar badge, and Manila districts."""


def _id(obj):
    return obj["id"] if isinstance(obj, dict) else obj.id


def test_sixteen_districts(client):
    d = client.get("/districts").json()
    assert len(d) == 16 and "Tondo" in d and "Sampaloc" in d


def test_city_admin_sets_district(client, admin_headers, barangay):
    r = client.put(
        "/barangays/%d/district" % _id(barangay), json={"district": "Tondo"}, headers=admin_headers
    )
    assert r.status_code == 200, r.text
    rows = {b["id"]: b for b in client.get("/barangays").json()}
    assert rows[_id(barangay)]["district"] == "Tondo"


def test_unknown_district_rejected(client, admin_headers, barangay):
    r = client.put(
        "/barangays/%d/district" % _id(barangay), json={"district": "Makati"}, headers=admin_headers
    )
    assert r.status_code == 422


def test_official_cannot_set_district(client, staff_headers, barangay):
    r = client.put(
        "/barangays/%d/district" % _id(barangay), json={"district": "Tondo"}, headers=staff_headers
    )
    assert r.status_code == 403


def test_registration_with_district(client, monkeypatch):
    monkeypatch.delenv("REGISTRATION_CODE", raising=False)
    body = {
        "barangay_name": "Barangay 588, Zone 58",
        "district": "Sampaloc",
        "designation": "Barangay Chairman",
        "employee_id": "EMP-001",
        "full_name": "Ana Cruz",
        "email": "ana.cruz@example.com",
        "mobile_number": "09171234567",
        "password": "Evacuate2026",
    }
    r = client.post("/register", json=body)
    assert r.status_code == 201, r.text
    rows = {b["name"]: b for b in client.get("/barangays").json()}
    assert rows["Barangay 588, Zone 58"]["district"] == "Sampaloc"


def test_sync_info_on_a_barangay_server(client, admin_headers, evacuee):
    r = client.get("/sync/info", headers=admin_headers)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["role"] == "server" and d["waiting"] >= 1 and d["configured"] is False


def test_sync_info_on_the_hub(client, admin_headers, monkeypatch):
    monkeypatch.setenv("SYNC_KEY", "k")
    row = {
        "table": "barangays",
        "uuid": "11111111-1111-4111-8111-111111111111",
        "data": {"name": "Barangay 1", "updated_at": "2026-10-06T08:00:00", "origin": "server-z"},
    }
    client.post(
        "/sync/push",
        json={"server_id": "server-z", "rows": [row], "tombstones": []},
        headers={"X-Sync-Key": "k"},
    )
    d = client.get("/sync/info", headers=admin_headers).json()
    assert d["role"] == "hub" and d["servers"][0]["server_id"] == "server-z"


def test_sync_info_requires_login(client):
    client.headers.pop("Authorization", None)  # this test checks the not-signed-in case
    assert client.get("/sync/info").status_code == 401
