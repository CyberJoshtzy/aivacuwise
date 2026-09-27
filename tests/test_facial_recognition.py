"""Covers the two endpoints the Raspberry Pi client depends on:
POST /evacuees/{id}/facial_embedding (used by enroll.py) and
GET /evacuees/enrolled_faces (used by recognize.py to load known faces).

These don't touch the camera or face_recognition library at all - they just
confirm the backend correctly stores and returns whatever embedding vector
it's given. Camera/matching accuracy is tested separately on the Pi itself,
not something a backend unit test can meaningfully check.
"""


def test_set_and_retrieve_facial_embedding(client, staff_headers, evacuee):
    fake_embedding = [0.1] * 128  # face_recognition embeddings are 128-d

    set_resp = client.post(
        f"/evacuees/{evacuee['id']}/facial_embedding",
        json={"embedding": fake_embedding},
        headers=staff_headers,
    )
    assert set_resp.status_code == 200, set_resp.text

    enrolled = client.get("/evacuees/enrolled_faces", headers=staff_headers)
    assert enrolled.status_code == 200
    matches = [f for f in enrolled.json() if f["evacuee_id"] == evacuee["id"]]
    assert len(matches) == 1
    assert matches[0]["embedding"] == fake_embedding
    assert matches[0]["full_name"] == "Juan Dela Cruz"


def test_facial_embedding_marks_identification_method(client, staff_headers, evacuee):
    client.post(
        f"/evacuees/{evacuee['id']}/facial_embedding",
        json={"embedding": [0.2] * 128},
        headers=staff_headers,
    )
    listing = client.get("/evacuees", headers=staff_headers)
    assert listing.status_code == 200
    match = [e for e in listing.json() if e["id"] == evacuee["id"]][0]
    assert match["identification_method"] == "facial_recognition"


def test_enrolled_faces_excludes_evacuees_without_embeddings(
    client, staff_headers, evacuee
):
    # `evacuee` was never given a facial_embedding, so it must not appear here.
    enrolled = client.get("/evacuees/enrolled_faces", headers=staff_headers)
    ids = [f["evacuee_id"] for f in enrolled.json()]
    assert evacuee["id"] not in ids


def test_facial_embedding_rejects_unknown_evacuee(client, staff_headers):
    resp = client.post(
        "/evacuees/999999/facial_embedding",
        json={"embedding": [0.1] * 128},
        headers=staff_headers,
    )
    assert resp.status_code == 404
