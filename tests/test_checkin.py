"""Covers check-in, walk-in registration, and transfers - including the
'occupancy accuracy fix' documented in the setup log (an evacuee must not
appear at two centers at once after being transferred)."""


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


def test_transfer_moves_evacuee_between_centers(
    client, staff_headers, evacuee, center, second_center
):
    checkin_resp = client.post(
        "/checkin",
        json={
            "evacuee_id": evacuee["id"],
            "evacuation_center_id": center["id"],
            "event_type": "check_in",
        },
        headers=staff_headers,
    )
    assert checkin_resp.status_code in (200, 201)

    transfer_resp = client.post(
        "/transfers",
        json={
            "evacuee_id": evacuee["id"],
            "from_center_id": center["id"],
            "to_center_id": second_center["id"],
        },
        headers=staff_headers,
    )
    assert transfer_resp.status_code in (200, 201), transfer_resp.text

    # This is the bug the setup log calls out by name: before the fix, a
    # transferred evacuee showed up at BOTH centers because the query only
    # checked "does any check_in row exist", not "is this their latest event".
    old_listing = client.get(
        f"/evacuation_centers/{center['id']}/evacuees", headers=staff_headers
    )
    new_listing = client.get(
        f"/evacuation_centers/{second_center['id']}/evacuees", headers=staff_headers
    )
    old_names = [e["full_name"] for e in old_listing.json()]
    new_names = [e["full_name"] for e in new_listing.json()]

    assert "Juan Dela Cruz" not in old_names
    assert "Juan Dela Cruz" in new_names


def test_transfer_rejects_mismatched_source_center(
    client, staff_headers, evacuee, center, second_center
):
    # evacuee was never checked in anywhere, so claiming they're transferring
    # FROM `center` should be rejected rather than silently accepted.
    resp = client.post(
        "/transfers",
        json={
            "evacuee_id": evacuee["id"],
            "from_center_id": center["id"],
            "to_center_id": second_center["id"],
        },
        headers=staff_headers,
    )
    assert resp.status_code >= 400


def test_evacuee_history_records_both_events(
    client, staff_headers, evacuee, center, second_center
):
    client.post(
        "/checkin",
        json={
            "evacuee_id": evacuee["id"],
            "evacuation_center_id": center["id"],
            "event_type": "check_in",
        },
        headers=staff_headers,
    )
    client.post(
        "/transfers",
        json={
            "evacuee_id": evacuee["id"],
            "from_center_id": center["id"],
            "to_center_id": second_center["id"],
        },
        headers=staff_headers,
    )

    history = client.get(f"/evacuees/{evacuee['id']}/history", headers=staff_headers)
    assert history.status_code == 200
    assert len(history.json()) >= 2
