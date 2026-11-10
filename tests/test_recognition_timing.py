"""Recognition speed measurements sent by the entrance camera (thesis Chapter 4)."""

import time


def _report(client, headers, evacuee_id, center_id, seen, rec, saved):
    return client.post(
        "/recognition/timings",
        json={
            "evacuee_id": evacuee_id,
            "center_id": center_id,
            "action": "check_in",
            "face_seen_at": seen,
            "recognized_at": rec,
            "saved_at": saved,
            "frame_ms": 412.5,
            "distance": 0.4381,
            "width": 1920,
            "height": 1080,
            "frame_scale": 0.25,
        },
        headers=headers,
    )


def test_timing_is_stored_with_computed_durations(client, staff_headers, evacuee, center):
    t0 = time.time()
    resp = _report(client, staff_headers, evacuee["id"], center["id"], t0, t0 + 0.84, t0 + 0.96)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["recognition_s"] == 0.84
    assert body["total_s"] == 0.96

    latest = client.get(
        "/recognition/timings/latest", params={"center_id": center["id"]}, headers=staff_headers
    )
    assert latest.status_code == 200, latest.text
    row = latest.json()[str(evacuee["id"])]
    assert row["save_s"] == 0.12
    assert row["width"] == 1920


def test_csv_download_has_one_row_per_measurement(client, staff_headers, evacuee, center):
    t0 = time.time()
    _report(client, staff_headers, evacuee["id"], center["id"], t0, t0 + 0.5, t0 + 0.6)
    _report(client, staff_headers, evacuee["id"], center["id"], t0, t0 + 1.2, t0 + 1.3)
    resp = client.get("/recognition/timings.csv", headers=staff_headers)
    assert resp.status_code == 200, resp.text
    lines = [x for x in resp.text.lstrip("﻿").splitlines() if x.strip()]
    assert lines[0].startswith("No.,Date,Evacuee")
    assert len(lines) == 3  # header + 2 measurements
    assert "Juan Dela Cruz" in lines[1]


def test_bad_action_is_rejected(client, staff_headers, evacuee, center):
    resp = client.post(
        "/recognition/timings",
        json={"evacuee_id": evacuee["id"], "center_id": center["id"], "action": "dance"},
        headers=staff_headers,
    )
    assert resp.status_code == 422


def test_needs_sign_in(client, center):
    resp = client.get("/recognition/timings.csv")
    assert resp.status_code == 401
