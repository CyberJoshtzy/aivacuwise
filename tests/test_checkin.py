"""Covers check-in and walk-in registration, including the 'occupancy
accuracy fix' (an evacuee must not appear at two centers at once)."""


def test_checkin_appears_in_center_list(client, staff_headers, evacuee, center):
    resp = client.post(
        "/checkin",
        json={
            "evacuee_id": evacuee["id"],
            "evacuation_center_id": center["id"],
            "event_type": "check_in",
        },
        headers=staff_headers,
    )
    assert resp.status_code in (200, 201), resp.text

    listing = client.get(
        f"/evacuation_centers/{center['id']}/evacuees", headers=staff_headers
    )
    assert listing.status_code == 200
    names = [e["full_name"] for e in listing.json()]
    assert "Juan Dela Cruz" in names


def test_walkin_checkin_creates_and_checks_in(client, staff_headers, center, barangay):
    resp = client.post(
        "/checkin/walkin",
        json={
            "full_name": "Maria Santos",
            "birthdate": "1985-05-05",
            "sex": "female",
            "address": "321 Walkin St",
            "contact_number": "09179876543",
            "registered_barangay_id": barangay["id"],
            "evacuation_center_id": center["id"],
        },
        headers=staff_headers,
    )
    assert resp.status_code in (200, 201), resp.text

    listing = client.get(
        f"/evacuation_centers/{center['id']}/evacuees", headers=staff_headers
    )
    names = [e["full_name"] for e in listing.json()]
    assert "Maria Santos" in names


def test_checkin_at_second_center_moves_evacuee(
    client, staff_headers, evacuee, center, second_center
):
    # Occupancy accuracy fix: an evacuee counts only at the center of their
    # latest check-in, so arriving at a second center moves them there.
    for c in (center, second_center):
        r = client.post(
            "/checkin",
            json={"evacuee_id": evacuee["id"], "evacuation_center_id": c["id"], "event_type": "check_in"},
            headers=staff_headers,
        )
        assert r.status_code in (200, 201), r.text

    old_names = [e["full_name"] for e in client.get(f"/evacuation_centers/{center['id']}/evacuees", headers=staff_headers).json()]
    new_names = [e["full_name"] for e in client.get(f"/evacuation_centers/{second_center['id']}/evacuees", headers=staff_headers).json()]
    assert "Juan Dela Cruz" not in old_names
    assert "Juan Dela Cruz" in new_names

    history = client.get(f"/evacuees/{evacuee['id']}/history", headers=staff_headers)
    assert history.status_code == 200
    assert len(history.json()) >= 2


def test_transfer_endpoints_are_removed(client, staff_headers):
    assert client.get("/transfers", headers=staff_headers).status_code in (404, 405)
