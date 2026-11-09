"""Entrance camera heartbeat: the Pi reports in, the pages read Camera on/off."""


def test_status_empty_then_online(client, staff_headers, center):
    camera_status_mod = __import__("camera_status")
    camera_status_mod._last_seen.clear()
    assert client.get("/camera/status", headers=staff_headers).json() == []
    r = client.post("/camera/heartbeat", json={"center_id": center["id"]}, headers=staff_headers)
    assert r.status_code == 200
    rows = client.get("/camera/status", headers=staff_headers).json()
    assert len(rows) == 1
    assert rows[0]["center_id"] == center["id"]
    assert rows[0]["kind"] == "entrance"
    assert rows[0]["online"] is True
    assert rows[0]["stream_url"] is None


def test_stream_url_from_heartbeat(client, staff_headers, center):
    camera_status_mod = __import__("camera_status")
    camera_status_mod._last_seen.clear()
    client.post(
        "/camera/heartbeat",
        json={"center_id": center["id"], "stream_port": 8081},
        headers=staff_headers,
    )
    row = client.get("/camera/status", headers=staff_headers).json()[0]
    assert row["stream_url"].endswith(":8081/stream.mjpg")


def test_old_heartbeat_is_offline(client, staff_headers, center):
    from datetime import UTC, datetime, timedelta

    camera_status_mod = __import__("camera_status")
    camera_status_mod._last_seen.clear()
    camera_status_mod._last_seen[(center["id"], "entrance")] = {
        "at": datetime.now(UTC) - timedelta(minutes=5),
        "host": "192.168.100.41",
        "stream_port": None,
    }
    rows = client.get("/camera/status", headers=staff_headers).json()
    assert rows[0]["online"] is False


def test_heartbeat_requires_login(client, center):
    client.headers.pop("Authorization", None)
    r = client.post("/camera/heartbeat", json={"center_id": center["id"]})
    assert r.status_code == 401
