"""Pause and resume an evacuation; finishing checks everyone out."""


def _start(client, headers, center):
    r = client.post("/incidents", json={"disaster_type": "Flood", "evacuation_center_id": center["id"]}, headers=headers)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def test_pause_then_resume(client, staff_headers, center):
    iid = _start(client, staff_headers, center)
    r = client.post("/incidents/%d/end" % iid, json={"finish": False}, headers=staff_headers)
    assert r.status_code == 200 and r.json()["finished"] is False and r.json()["active"] is False
    r = client.post("/incidents/%d/resume" % iid, headers=staff_headers)
    assert r.status_code == 200, r.text
    assert r.json()["active"] is True and r.json()["ended_at"] is None


def test_finish_checks_everyone_out_and_cannot_resume(client, staff_headers, evacuee, center):
    iid = _start(client, staff_headers, center)
    client.post("/checkin", json={"evacuee_id": evacuee["id"], "evacuation_center_id": center["id"], "event_type": "check_in"}, headers=staff_headers)
    assert len(client.get("/evacuation_centers/%d/evacuees" % center["id"], headers=staff_headers).json()) == 1
    r = client.post("/incidents/%d/end" % iid, json={"finish": True}, headers=staff_headers)
    assert r.status_code == 200 and r.json()["finished"] is True
    assert client.get("/evacuation_centers/%d/evacuees" % center["id"], headers=staff_headers).json() == []
    hist = client.get("/evacuees/%d/history" % evacuee["id"], headers=staff_headers).json()
    assert hist[0]["event_type"] == "check_out"
    assert client.post("/incidents/%d/resume" % iid, headers=staff_headers).status_code == 409


def test_end_without_body_still_works(client, staff_headers, center):
    iid = _start(client, staff_headers, center)
    assert client.post("/incidents/%d/end" % iid, headers=staff_headers).status_code == 200
