"""Resident sign in with the mobile number only (name fields were removed from the page)."""

import pytest

import resident

NO_AUTH = {"Authorization": ""}


@pytest.fixture(autouse=True)
def _clear_fail_counter():
    resident._fails.clear()
    yield
    resident._fails.clear()


def _family(client, staff_headers, barangay):
    h = client.post(
        "/households",
        json={
            "registered_barangay_id": barangay["id"],
            "members": [
                {
                    "full_name": "Lorna Santos",
                    "birthdate": "1980-05-02",
                    "sex": "Female",
                    "address": "1 Test St",
                    "contact_number": "09172309422",
                    "is_head_of_family": True,
                },
                {
                    "full_name": "Mika Santos",
                    "birthdate": "2015-08-20",
                    "sex": "Female",
                    "address": "1 Test St",
                    "contact_number": None,
                    "is_head_of_family": False,
                },
            ],
        },
        headers=staff_headers,
    )
    assert h.status_code in (200, 201), h.text
    return h.json()


def test_mobile_number_alone_signs_in_the_head_of_family(client, staff_headers, barangay):
    _family(client, staff_headers, barangay)
    r = client.post(
        "/resident/login", json={"mobile_number": "0917 230 9422"}, headers=NO_AUTH
    )
    assert r.status_code == 200, r.text
    assert r.json()["full_name"] == "Lorna Santos"
    me = client.get(
        "/resident/me", headers={"Authorization": "Resident " + r.json()["token"]}
    )
    assert me.status_code == 200, me.text


def test_unknown_mobile_number_is_rejected(client, staff_headers, barangay):
    _family(client, staff_headers, barangay)
    r = client.post("/resident/login", json={"mobile_number": "09990000000"}, headers=NO_AUTH)
    assert r.status_code == 401


def test_invalid_mobile_number_is_rejected(client):
    r = client.post("/resident/login", json={"mobile_number": "12345"}, headers=NO_AUTH)
    assert r.status_code == 422


def test_name_and_mobile_still_work_for_older_clients(client, staff_headers, barangay):
    _family(client, staff_headers, barangay)
    r = client.post(
        "/resident/login",
        json={"first_name": "Mika", "last_name": "Santos", "mobile_number": "09172309422"},
        headers=NO_AUTH,
    )
    assert r.status_code == 200, r.text
    assert r.json()["full_name"] == "Mika Santos"
