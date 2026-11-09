"""Ai-Vacuwise entrance camera: recognizes registered evacuees walking past and checks them in.

Same approach as the Raspberry Pi's recognize.py: face_recognition (dlib), 0.6 tolerance,
cooldown per person, enrolled faces reloaded every minute. If a recognized person is already
checked in at a different center, a transfer is recorded instead of a plain check-in.

Run:  ~/bilislikas2.0/venv/bin/python recognize.py      Stop: press q in the window, or Ctrl+C.
"""

import json
import sys
import time

import config
import cv2
import face_recognition
import numpy as np
import requests


class Backend:
    def __init__(self):
        self.base = config.BACKEND_URL.rstrip("/")
        self.token = None

    def login(self):
        r = requests.post(
            self.base + "/login",
            data={"username": config.USERNAME, "password": config.PASSWORD},
            timeout=10,
        )
        if r.status_code != 200:
            sys.exit("Login failed (%s). Check USERNAME and PASSWORD in config.py." % r.status_code)
        self.token = r.json()["access_token"]

    def call(self, method, path, **kw):
        for attempt in (1, 2):
            headers = {"Authorization": "Bearer " + (self.token or "")}
            r = requests.request(method, self.base + path, headers=headers, timeout=10, **kw)
            if r.status_code == 401 and attempt == 1:
                self.login()  # token expired after 8 hours: sign in again and retry once
                continue
            return r


def pick(d, *keys):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def parse_faces(rows):
    """Reads GET /evacuees/enrolled_faces without assuming exact field names."""
    ids, names, vecs = [], [], []
    for row in rows or []:
        eid = pick(row, "evacuee_id", "id")
        name = pick(row, "full_name", "name") or ("Evacuee #%s" % eid)
        vec = pick(row, "facial_embedding", "embedding", "encoding")
        if vec is None:
            vec = next((v for v in row.values() if isinstance(v, list) and len(v) == 128), None)
        if isinstance(vec, str):
            try:
                vec = json.loads(vec)
            except ValueError:
                vec = None
        if eid is None or not isinstance(vec, list) or len(vec) != 128:
            continue
        ids.append(int(eid))
        names.append(name)
        vecs.append(np.array(vec, dtype=np.float64))
    return ids, names, vecs


def main():
    api = Backend()
    api.login()
    print(
        "Signed in to %s as %s. Camera guards evacuation center %s."
        % (api.base, config.USERNAME, config.EVACUATION_CENTER_ID)
    )

    cam = cv2.VideoCapture(config.CAMERA_INDEX, cv2.CAP_V4L2)
    cam.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # always use the newest frame (avoids the multi-second lag)
    if not cam.isOpened():
        sys.exit(
            "Cannot open camera %s. Close any browser tab using the webcam and try again."
            % config.CAMERA_INDEX
        )

    ids, names, vecs, where = [], [], [], {}
    last_load = 0.0
    last_action = {}  # evacuee id -> time of last check-in/transfer
    scale = config.FRAME_SCALE

    try:
        while True:
            now = time.time()
            if now - last_load > config.ENROLLED_FACES_REFRESH_SECONDS:
                r = api.call("GET", "/evacuees/enrolled_faces")
                if r.status_code == 200:
                    ids, names, vecs = parse_faces(r.json())
                s = api.call("GET", "/dashboard/summary")
                if s.status_code == 200:
                    where = {}
                    for b in s.json().get("barangays", []):
                        for c in b.get("centers", []):
                            for p in c.get("evacuees", []):
                                where[p["id"]] = c["id"]
                print("Loaded %d enrolled face(s)." % len(ids))
                last_load = now

            ok, frame = cam.read()
            if not ok:
                time.sleep(0.05)
                continue
            small = cv2.resize(frame, (0, 0), fx=scale, fy=scale)
            rgb = np.ascontiguousarray(small[:, :, ::-1])
            locs = face_recognition.face_locations(rgb, model="hog")
            encs = face_recognition.face_encodings(rgb, known_face_locations=locs)

            for (top, right, bottom, left), enc in zip(locs, encs):  # noqa: B905
                label, color = "Not registered", (0, 0, 220)
                if vecs:
                    dist = face_recognition.face_distance(vecs, enc)
                    i = int(np.argmin(dist))
                    if dist[i] <= config.MATCH_TOLERANCE:
                        eid, name = ids[i], names[i]
                        label, color = "%s (%.2f)" % (name, dist[i]), (0, 170, 0)
                        if now - last_action.get(eid, 0) > config.CHECKIN_COOLDOWN_SECONDS:
                            last_action[eid] = now
                            here = where.get(eid)
                            if here == config.EVACUATION_CENTER_ID:
                                print(
                                    "%s is already inside this center (match %.3f)."
                                    % (name, dist[i])
                                )
                            elif here is not None:
                                r = api.call(
                                    "POST",
                                    "/transfers",
                                    json={
                                        "evacuee_id": eid,
                                        "from_center_id": here,
                                        "to_center_id": config.EVACUATION_CENTER_ID,
                                    },
                                )
                                if r.status_code in (200, 201):
                                    print(
                                        "TRANSFERRED %s from center %s (match %.3f)"
                                        % (name, here, dist[i])
                                    )
                                    where[eid] = config.EVACUATION_CENTER_ID
                                else:
                                    print("Transfer failed for %s: %s" % (name, r.text[:120]))
                            else:
                                r = api.call(
                                    "POST",
                                    "/checkin",
                                    json={
                                        "evacuee_id": eid,
                                        "evacuation_center_id": config.EVACUATION_CENTER_ID,
                                        "event_type": "check_in",
                                    },
                                )
                                if r.status_code in (200, 201):
                                    print("CHECKED IN %s (match %.3f)" % (name, dist[i]))
                                    where[eid] = config.EVACUATION_CENTER_ID
                                else:
                                    print("Check-in failed for %s: %s" % (name, r.text[:120]))
                if config.SHOW_PREVIEW:
                    t, r_, b, l = [int(v / scale) for v in (top, right, bottom, left)]  # noqa: E741
                    cv2.rectangle(frame, (l, t), (r_, b), color, 2)
                    cv2.rectangle(frame, (l, b), (r_, b + 28), color, cv2.FILLED)
                    cv2.putText(
                        frame,
                        label,
                        (l + 6, b + 20),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        (255, 255, 255),
                        2,
                    )

            if config.SHOW_PREVIEW:
                cv2.imshow("Ai-Vacuwise entrance camera (press q to stop)", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    except KeyboardInterrupt:
        pass
    finally:
        cam.release()
        if config.SHOW_PREVIEW:
            cv2.destroyAllWindows()
        print("Entrance camera stopped.")


if __name__ == "__main__":
    main()
