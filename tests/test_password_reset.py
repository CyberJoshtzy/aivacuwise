"""Forgot password: 6-digit code by email. Real sending is replaced by a fake that records the code."""
import pytest

import password_reset

EMAIL = "reset.official@example.com"


@pytest.fixture
def sent(monkeypatch):
    box = []
    monkeypatch.setattr(password_reset, "send_email", lambda to, code: box.append(("email", to, code)))
    return box


@pytest.fixture
def official(client):
    r = client.post("/register", json={
        "barangay_name": "Barangay Reset Test", "designation": "Barangay Secretary",
        "full_name": "Juan Santos Dela Cruz", "email": EMAIL, "mobile_number": "09171234567",
        "password": "OldPass123", "district": "Tondo",
    })
    assert r.status_code == 201, r.text
    return EMAIL


def _login(client, email, pw):
    return client.post("/login", data={"username": email, "password": pw})


def test_forgot_offers_masked_email_only(client, official):
    r = client.post("/password/forgot", json={"email": official})
    assert r.status_code == 200
    opts = r.json()["options"]
    assert [o["channel"] for o in opts] == ["email"]
    assert opts[0]["hint"] == "re***@example.com"


def test_forgot_unknown_email(client):
    r = client.post("/password/forgot", json={"email": "nobody@example.com"})
    assert r.status_code == 404


def test_full_reset_flow(client, official, sent):
    r = client.post("/password/send", json={"email": official})
    assert r.status_code == 200, r.text
    assert sent[-1][0] == "email"
    code = sent[-1][2]
    assert len(code) == 6 and code.isdigit()
    assert client.post("/password/verify", json={"email": official, "code": code}).status_code == 200
    r = client.post("/password/reset", json={"email": official, "code": code, "new_password": "NewPass456"})
    assert r.status_code == 200, r.text
    assert _login(client, official, "NewPass456").status_code == 200
    assert _login(client, official, "OldPass123").status_code == 401
    again = client.post("/password/reset", json={"email": official, "code": code, "new_password": "Another789"})
    assert again.status_code == 400  # a code works only once


def test_wrong_code_is_counted_and_locked(client, official, sent):
    client.post("/password/send", json={"email": official, "channel": "email"})
    real = sent[-1][2]
    wrong = "000000" if real != "000000" else "111111"
    for _ in range(password_reset.MAX_ATTEMPTS):
        assert client.post("/password/verify", json={"email": official, "code": wrong}).status_code == 400
    r = client.post("/password/verify", json={"email": official, "code": real})
    assert r.status_code == 429


def test_resend_wait(client, official, sent):
    assert client.post("/password/send", json={"email": official, "channel": "email"}).status_code == 200
    r = client.post("/password/send", json={"email": official, "channel": "email"})
    assert r.status_code == 429


def test_weak_new_password_rejected(client, official, sent):
    client.post("/password/send", json={"email": official, "channel": "email"})
    r = client.post("/password/reset", json={"email": official, "code": sent[-1][2], "new_password": "short"})
    assert r.status_code == 422


def test_not_configured_gives_clear_message(client, official, monkeypatch):
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    r = client.post("/password/send", json={"email": official, "channel": "email"})
    assert r.status_code == 503
    assert "not set up" in r.json()["detail"]



def test_sms_channel_is_rejected(client, official, sent):
    r = client.post("/password/send", json={"email": official, "channel": "sms"})
    assert r.status_code == 422
