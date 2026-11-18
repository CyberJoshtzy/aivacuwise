"""Resident sign in: mobile number, then a 6-digit code (OTP) sent by SMS."""

import pytest

import resident

NO_AUTH = {"Authorization": ""}


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    for d in (resident._fails, resident._otps, resident._otp_sent):
        d.clear()
    monkeypatch.setattr(resident, "OTP_DEBUG", True)  # return the code so tests can use it
    yield
    for d in (resident._fails, resident._otps, resident._otp_sent):
        d.clear()


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


def _ask_code(client, body):
    r = client.post("/resident/login", json=body, headers=NO_AUTH)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["otp_required"] is True and "token" not in data
    return data


def test_mobile_then_code_signs_in_head_of_family(client, staff_headers, barangay):
    _family(client, staff_headers, barangay)
    data = _ask_code(client, {"mobile_number": "0917 230 9422"})
    assert data["sent_to"] == "0917 *** 9422"
    r = client.post(
        "/resident/verify-otp",
        json={"challenge": data["challenge"], "code": data["dev_code"]},
        headers=NO_AUTH,
    )
    assert r.status_code == 200, r.text
    assert r.json()["full_name"] == "Lorna Santos"
    me = client.get("/resident/me", headers={"Authorization": "Resident " + r.json()["token"]})
    assert me.status_code == 200, me.text


def test_code_is_queued_as_sms(client, staff_headers, barangay, db_session):
    import sms

    _family(client, staff_headers, barangay)
    _ask_code(client, {"mobile_number": "09172309422"})
    msg = db_session.query(sms.SmsMessage).filter_by(kind="otp").one()
    assert msg.phone == "+639172309422" and "sign-in code" in msg.body


def test_wrong_code_is_rejected_and_code_is_single_use(client, staff_headers, barangay):
    _family(client, staff_headers, barangay)
    data = _ask_code(client, {"mobile_number": "09172309422"})
    wrong = "000000" if data["dev_code"] != "000000" else "111111"
    r = client.post(
        "/resident/verify-otp", json={"challenge": data["challenge"], "code": wrong}, headers=NO_AUTH
    )
    assert r.status_code == 401
    ok = client.post(
        "/resident/verify-otp",
        json={"challenge": data["challenge"], "code": data["dev_code"]},
        headers=NO_AUTH,
    )
    assert ok.status_code == 200
    again = client.post(
        "/resident/verify-otp",
        json={"challenge": data["challenge"], "code": data["dev_code"]},
        headers=NO_AUTH,
    )
    assert again.status_code == 410


def test_resend_is_limited(client, staff_headers, barangay):
    _family(client, staff_headers, barangay)
    _ask_code(client, {"mobile_number": "09172309422"})
    r = client.post("/resident/login", json={"mobile_number": "09172309422"}, headers=NO_AUTH)
    assert r.status_code == 429


def test_unknown_mobile_number_is_rejected(client, staff_headers, barangay):
    _family(client, staff_headers, barangay)
    r = client.post("/resident/login", json={"mobile_number": "09990000000"}, headers=NO_AUTH)
    assert r.status_code == 401


def test_invalid_mobile_number_is_rejected(client):
    r = client.post("/resident/login", json={"mobile_number": "12345"}, headers=NO_AUTH)
    assert r.status_code == 422


def test_name_and_mobile_still_work_for_older_clients(client, staff_headers, barangay):
    _family(client, staff_headers, barangay)
    data = _ask_code(
        client, {"first_name": "Mika", "last_name": "Santos", "mobile_number": "09172309422"}
    )
    r = client.post(
        "/resident/verify-otp",
        json={"challenge": data["challenge"], "code": data["dev_code"]},
        headers=NO_AUTH,
    )
    assert r.status_code == 200, r.text
    assert r.json()["full_name"] == "Mika Santos"
