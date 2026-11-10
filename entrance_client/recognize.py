"""Ai-Vacuwise entrance camera: recognizes registered evacuees walking past and checks them in.

Same approach as the Raspberry Pi's recognize.py: face_recognition (dlib), 0.6 tolerance,
cooldown per person, enrolled faces reloaded every minute. If a recognized person is already
checked in at a different center, a transfer is recorded instead of a plain check-in.

Run:  ~/ai-vacuwise/venv/bin/python recognize.py      Stop: press q in the window, or Ctrl+C.
"""

import json
import os
import sys
import time

import config
import cv2
import face_recognition
import numpy as np
import requests

# The background service (ai-vacuwise-entrance-camera) has no screen, so it runs without the preview window.
if os.environ.get("AIVACUWISE_HEADLESS") == "1":
    config.SHOW_PREVIEW = False


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


class Stream:
    """Shares the newest camera picture (with face boxes and names) for the TV Mode page.

    GET http://<pi>:STREAM_PORT/stream.mjpg   live picture (MJPEG)
    GET http://<pi>:STREAM_PORT/health        {"ok": true}
    """

    def __init__(self, port):
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        self.port = port
        self.jpeg = None
        self.count = 0
        self.cond = threading.Condition()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                path = self.path.split("?")[0]
                if path == "/health":
                    body = b'{"ok": true}'
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if path != "/stream.mjpg":
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                seen = 0
                try:
                    while True:
                        with outer.cond:
                            outer.cond.wait_for(lambda: outer.count > seen, timeout=5)
                            seen, data = outer.count, outer.jpeg
                        if data:
                            self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n")
                            self.wfile.write(b"Content-Length: %d\r\n\r\n" % len(data))
                            self.wfile.write(data + b"\r\n")
                except (BrokenPipeError, ConnectionResetError):
                    pass  # the TV page was closed

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.last = 0.0

    def push(self, frame):
        now = time.time()
        if now - self.last < 0.1:  # about 10 pictures per second is enough for the TV
            return
        self.last = now
        h, w = frame.shape[:2]
        sw = int(getattr(config, "STREAM_WIDTH", 960))
        if w > sw:
            frame = cv2.resize(frame, (sw, int(h * sw / w)))
        q = int(getattr(config, "STREAM_QUALITY", 80))
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), q])
        if ok:
            with self.cond:
                self.jpeg = buf.tobytes()
                self.count += 1
                self.cond.notify_all()


def find_camera(setting):
    """Returns what to open with OpenCV.

    setting = 0, 1, ...   a camera number (laptop webcam, or a Pi 4 with one USB webcam)
    setting = "usb"       the first USB webcam (needed on a Raspberry Pi 5, where the
                          Camera Module 3 and the Pi's video hardware also appear as cameras)
    setting = "/dev/..."  an exact device path
    """
    if setting != "usb":
        return setting
    import glob
    import os

    for pattern in ("/dev/v4l/by-id/usb-*-video-index0", "/dev/v4l/by-path/*usb*-video-index0"):
        found = sorted(glob.glob(pattern))
        if found:
            return os.path.realpath(found[0])
    sys.exit("No USB webcam found. Plug the webcam into a USB port of the Pi, then run again.")


def main():
    api = Backend()
    api.login()
    print(
        "Signed in to %s as %s. Camera guards evacuation center %s."
        % (api.base, config.USERNAME, config.EVACUATION_CENTER_ID)
    )

    device = find_camera(config.CAMERA_INDEX)
    cam = cv2.VideoCapture(device, cv2.CAP_V4L2)
    cam.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # always use the newest frame (avoids the multi-second lag)
    # Picture size from the webcam. MJPG lets USB webcams send large pictures at full speed.
    cam_w = int(getattr(config, "CAMERA_WIDTH", 0) or 0)
    cam_h = int(getattr(config, "CAMERA_HEIGHT", 0) or 0)
    if cam_w and cam_h:
        cam.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cam.set(cv2.CAP_PROP_FRAME_WIDTH, cam_w)
        cam.set(cv2.CAP_PROP_FRAME_HEIGHT, cam_h)
    if getattr(config, "CAMERA_FPS", 0):
        cam.set(cv2.CAP_PROP_FPS, int(config.CAMERA_FPS))
    if not cam.isOpened():
        sys.exit(
            "Cannot open camera %s. Check the USB webcam cable, and close any other program "
            "using it (for example a browser tab)." % device
        )
    ok, first = cam.read()  # report the size the webcam really sends, not the size asked for
    if ok:
        real_h, real_w = first.shape[:2]
    else:
        real_w, real_h = int(cam.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cam.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print("Entrance camera: %s at %dx%d" % (device, real_w, real_h))
    if cam_w and cam_h and (real_w, real_h) != (cam_w, cam_h):
        print(
            "Note: asked for %dx%d but the webcam sends %dx%d. Pick a size it offers: "
            "v4l2-ctl -d %s --list-formats-ext | grep Size" % (cam_w, cam_h, real_w, real_h, device)
        )
    stream = None
    port = getattr(config, "STREAM_PORT", 8081)
    if port:
        try:
            stream = Stream(port)
            print("Live picture for TV Mode: http://<this Pi's address>:%d/stream.mjpg" % port)
        except OSError as exc:
            print("Live picture not shared (port %s busy: %s)" % (port, exc))

    ids, names, vecs, where = [], [], [], {}
    last_load = 0.0
    last_action = {}  # evacuee id -> time of last check-in/transfer
    scale = config.FRAME_SCALE
    last_beat = 0.0  # last "camera is running" report to the server

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

            if now - last_beat > 15:  # lets the website show "Camera on"
                try:
                    api.call(
                        "POST",
                        "/camera/heartbeat",
                        json={
                            "center_id": config.EVACUATION_CENTER_ID,
                            "kind": "entrance",
                            "stream_port": stream.port if stream else None,
                        },
                    )
                except requests.RequestException:
                    pass  # server briefly unreachable; recognition keeps running
                last_beat = now

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
                shown = label
                if vecs:
                    dist = face_recognition.face_distance(vecs, enc)
                    i = int(np.argmin(dist))
                    if dist[i] <= config.MATCH_TOLERANCE:
                        eid, name = ids[i], names[i]
                        label, color = "%s (%.2f)" % (name, dist[i]), (0, 170, 0)
                        shown = name
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
                if config.SHOW_PREVIEW or stream:
                    t, r_, b, l = [int(v / scale) for v in (top, right, bottom, left)]  # noqa: E741
                    text = label if config.SHOW_PREVIEW else shown  # TV shows the name only
                    tw = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0][0]
                    cv2.rectangle(frame, (l, t), (r_, b), color, 3)
                    cv2.rectangle(frame, (l, b), (max(r_, l + tw + 14), b + 34), color, cv2.FILLED)
                    cv2.putText(
                        frame,
                        text,
                        (l + 7, b + 25),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.8,
                        (255, 255, 255),
                        2,
                    )

            if stream:
                stream.push(frame)

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
