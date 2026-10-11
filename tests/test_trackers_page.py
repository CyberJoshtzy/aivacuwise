"""Assigning a tracker to an evacuee and the Trackers page overview."""


def test_assign_tracker_and_overview(client, staff_headers, evacuee):
    r = client.put("/evacuees/%d/tracker" % evacuee["id"], json={"device_id": "IMEI-123456"}, headers=staff_headers)
    assert r.status_code == 200, r.text
    tid = r.json()["tracker"]["id"]
    ov = client.get("/trackers/overview", headers=staff_headers).json()
    row = next(x for x in ov if x["evacuee_id"] == evacuee["id"])
    assert row["device_id"] == "IMEI-123456" and row["latitude"] is None
    p = client.post("/gps_pings", json={"tracker_id": tid, "latitude": 14.6091, "longitude": 120.9890, "source": "test"}, headers=staff_headers)
    assert p.status_code in (200, 201), p.text
    row = next(x for x in client.get("/trackers/overview", headers=staff_headers).json() if x["evacuee_id"] == evacuee["id"])
    assert abs(row["latitude"] - 14.6091) < 1e-6


def test_tracker_cannot_be_given_to_two_people(client, staff_headers, evacuee, barangay, center):
    client.put("/evacuees/%d/tracker" % evacuee["id"], json={"device_id": "IMEI-777"}, headers=staff_headers)
    other = client.post("/checkin/walkin", json={"full_name": "Pedro Cruz", "birthdate": "1990-01-01", "sex": "Male", "address": "2 Test St",
                                                   "contact_number": None, "registered_barangay_id": barangay["id"],
                                                   "evacuation_center_id": center["id"]}, headers=staff_headers)
    assert other.status_code in (200, 201), other.text
    oid = other.json()["evacuee"]["id"]
    r = client.put("/evacuees/%d/tracker" % oid, json={"device_id": "IMEI-777"}, headers=staff_headers)
    assert r.status_code == 409


def test_removing_tracker(client, staff_headers, evacuee):
    client.put("/evacuees/%d/tracker" % evacuee["id"], json={"device_id": "IMEI-999"}, headers=staff_headers)
    r = client.put("/evacuees/%d/tracker" % evacuee["id"], json={"device_id": ""}, headers=staff_headers)
    assert r.status_code == 200 and r.json()["tracker"] is None
    assert all(x["evacuee_id"] != evacuee["id"] for x in client.get("/trackers/overview", headers=staff_headers).json())
