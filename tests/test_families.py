"""Families, infant guardian check-in, and typed home barangay."""


def _family_with_infant(client, staff_headers, barangay):
    h = client.post("/households", json={"registered_barangay_id": barangay["id"], "members": [{
        "full_name": "Ana Reyes", "birthdate": "1995-03-10", "sex": "Female",
        "address": "1 Test St", "contact_number": None, "is_head_of_family": True}]}, headers=staff_headers)
    assert h.status_code in (200, 201), h.text
    hid, mom = h.json()["id"], h.json()["members"][0]["id"]
    baby = client.post("/households/%d/members" % hid, json={
        "full_name": "Baby Reyes", "birthdate": "2026-01-15", "sex": "Male", "address": "1 Test St"}, headers=staff_headers)
    assert baby.status_code in (200, 201), baby.text
    return hid, mom, baby.json()["id"]


def test_family_size_and_listing(client, staff_headers, barangay):
    hid, mom, baby = _family_with_infant(client, staff_headers, barangay)
    r = client.put("/households/%d/size" % hid, json={"member_count": 4}, headers=staff_headers)
    assert r.status_code == 200, r.text
    fams = client.get("/barangays/%d/families" % barangay["id"], headers=staff_headers).json()
    fam = next(f for f in fams if f["id"] == hid)
    assert fam["member_count"] == 4 and fam["registered"] == 2
    assert fam["head_name"] == "Ana Reyes"
    assert [m["is_infant"] for m in fam["members"]] == [False, True]


def test_family_size_limits(client, staff_headers, barangay):
    hid, _, _ = _family_with_infant(client, staff_headers, barangay)
    assert client.put("/households/%d/size" % hid, json={"member_count": 0}, headers=staff_headers).status_code == 422


def test_infant_checked_in_with_guardian(client, staff_headers, barangay, center):
    hid, mom, baby = _family_with_infant(client, staff_headers, barangay)
    r = client.put("/evacuees/%d" % baby, json={"guardian_evacuee_id": mom, "home_barangay": "Barangay 194"}, headers=staff_headers)
    assert r.status_code == 200, r.text
    assert r.json()["guardian_evacuee_id"] == mom and r.json()["home_barangay"] == "Barangay 194"
    c = client.post("/checkin", json={"evacuee_id": mom, "evacuation_center_id": center["id"], "event_type": "check_in"}, headers=staff_headers)
    assert c.status_code in (200, 201), c.text
    names = [e["full_name"] for e in client.get("/evacuation_centers/%d/evacuees" % center["id"], headers=staff_headers).json()]
    assert "Ana Reyes" in names and "Baby Reyes" in names


def test_deleting_guardian_unlinks_infant(client, staff_headers, barangay):
    hid, mom, baby = _family_with_infant(client, staff_headers, barangay)
    client.put("/evacuees/%d" % baby, json={"guardian_evacuee_id": mom}, headers=staff_headers)
    assert client.delete("/evacuees/%d" % mom, headers=staff_headers).status_code == 200
    r = client.put("/evacuees/%d" % baby, json={"home_barangay": "Barangay 194"}, headers=staff_headers)
    assert r.json()["guardian_evacuee_id"] is None
