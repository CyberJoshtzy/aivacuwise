"""Tests for pre-registration: face encoding checks, adding household members, extra evacuee fields."""

import base64
import io


def _id(obj):
    return obj["id"] if isinstance(obj, dict) else obj.id


def _blank_jpeg():
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (320, 240), (255, 255, 255)).save(buf, format="JPEG")
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _household(client, headers, barangay):
    body = {
        "registered_barangay_id": _id(barangay),
        "members": [
            {
                "full_name": "Pedro Garcia",
                "birthdate": "1980-01-01",
                "sex": "Male",
                "address": "5 Lakandula Street",
                "contact_number": "09170000000",
                "is_head_of_family": True,
            }
        ],
    }
    r = client.post("/households", json=body, headers=headers)
    assert r.status_code in (200, 201), r.text
    return r.json()


def test_encode_requires_login(client):
    client.headers.pop("Authorization", None)  # this test checks the not-signed-in case
    assert client.post("/faces/encode", json={"images": [_blank_jpeg()]}).status_code == 401


def test_encode_reports_missing_face(client, admin_headers):
    r = client.post(
        "/faces/encode",
        json={"images": [_blank_jpeg()], "angles": ["front"]},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is False and body["embedding"] is None
    assert "No face found in the front photo" in body["photos"][0]["message"]


def test_encode_reports_unreadable_photo(client, admin_headers):
    r = client.post(
        "/faces/encode",
        json={"images": ["not-an-image"], "angles": ["left"]},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert "could not be read" in r.json()["photos"][0]["message"]


def test_encode_rejects_too_many_photos(client, admin_headers):
    assert (
        client.post(
            "/faces/encode", json={"images": [_blank_jpeg()] * 6}, headers=admin_headers
        ).status_code
        == 422
    )


def test_add_member_to_household(client, admin_headers, barangay):
    h = _household(client, admin_headers, barangay)
    r = client.post(
        "/households/%d/members" % h["id"],
        json={
            "full_name": "Luz Garcia",
            "birthdate": "1983-04-02",
            "sex": "Female",
            "address": "5 Lakandula Street",
            "civil_status": "Married",
            "special_needs": ["Pregnant"],
            "emergency_contact": "Pedro Garcia, 09170000000",
        },
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["household_id"] == h["id"] and m["is_head_of_family"] is False
    assert m["identification_method"] == "facial_recognition"
    assert m["special_needs"] == ["Pregnant"]


def test_update_and_read_extra_fields(client, admin_headers, evacuee):
    eid = _id(evacuee)
    r = client.put(
        "/evacuees/%d" % eid,
        json={
            "civil_status": "Single",
            "special_needs": ["PWD", "Senior citizen", "PWD"],
            "emergency_contact": "Ana Reyes, 09180000000",
        },
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["special_needs"] == ["PWD", "Senior citizen"]
    rows = {x["id"]: x for x in client.get("/evacuee_details", headers=admin_headers).json()}
    assert rows[eid]["emergency_contact"] == "Ana Reyes, 09180000000"
    assert rows[eid]["civil_status"] == "Single"
