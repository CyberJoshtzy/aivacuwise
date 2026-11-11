"""AiVacuwise pre-registration camera service (Raspberry Pi 5 + Camera Module 3).

Shares the Camera Module 3 with the Pre-Registration page on the laptop server, so the
barangay official can capture the left, front and right photos from any browser on the
local network. Face checks and encoding still run on the laptop (/faces/check, /faces/encode).

Endpoints (port 8080 by default, CORS open so the laptop page can read the images):
    GET /stream.mjpg     live preview (MJPEG) for the page
    GET /snapshot.jpg    newest frame as JPEG, preview size (used for the live face check)
    GET /photo.jpg       newest frame as JPEG, full size (used when a photo is captured)
    GET /health          {"ok": true, "camera": "...", "size": [w, h]}

Run on the Pi:   python3 ~/aivacuwise-pi/pi_camera/prereg_camera.py
Stop:            Ctrl+C   (or: sudo systemctl stop aivacuwise-prereg-camera)
Needs:           python3-picamera2 (preinstalled on Raspberry Pi OS), opencv-python
"""

import json
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---------------- settings ----------------
PORT = 8080
PHOTO_SIZE = (1296, 972)  # full-size capture (4:3); faces are encoded from this
PREVIEW_WIDTH = 640  # snapshot/stream width; height keeps 4:3
FPS = 15
JPEG_QUALITY = 85
# Camera Module 3 is mounted facing the evacuee. Set True if the picture is upside down.
ROTATE_180 = False
# ------------------------------------------

try:
    import cv2
except ImportError:
    sys.exit("OpenCV is missing. Run: pip install opencv-python --break-system-packages")


class Camera:
    """Keeps the newest frame from the Camera Module 3 in memory, as JPEG bytes."""

    def __init__(self):
        self.lock = threading.Condition()
        self.full_jpeg = None
        self.preview_jpeg = None
        self.frame_no = 0
        self.running = True
        self.name = "unknown"
        self.cam = None

    def start(self):
        try:
            from picamera2 import Picamera2
        except ImportError:
            sys.exit("picamera2 is missing. Run: sudo apt install -y python3-picamera2")
        infos = Picamera2.global_camera_info()
        if not infos:
            sys.exit(
                "No Camera Module found. Check the ribbon cable (contacts face the right way, "
                "both latches closed), then reboot the Pi."
            )
        self.name = infos[0].get("Model", "camera")
        self.cam = Picamera2(0)
        # RGB888 in Picamera2 is BGR byte order, which is what OpenCV expects.
        conf = self.cam.create_video_configuration(
            main={"size": PHOTO_SIZE, "format": "RGB888"},
            controls={"FrameRate": FPS},
            buffer_count=4,
        )
        self.cam.configure(conf)
        self.cam.start()
        try:  # Camera Module 3 has autofocus: keep refocusing as people move
            from libcamera import controls

            self.cam.set_controls({"AfMode": controls.AfModeEnum.Continuous})
        except Exception:
            pass  # older module without autofocus
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        enc = [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
        while self.running:
            frame = self.cam.capture_array("main")
            if ROTATE_180:
                frame = cv2.rotate(frame, cv2.ROTATE_180)
            h, w = frame.shape[:2]
            small = cv2.resize(frame, (PREVIEW_WIDTH, int(h * PREVIEW_WIDTH / w)))
            ok1, full = cv2.imencode(".jpg", frame, enc)
            ok2, prev = cv2.imencode(".jpg", small, enc)
            if ok1 and ok2:
                with self.lock:
                    self.full_jpeg = full.tobytes()
                    self.preview_jpeg = prev.tobytes()
                    self.frame_no += 1
                    self.lock.notify_all()

    def wait_frame(self, after, timeout=2.0):
        with self.lock:
            self.lock.wait_for(lambda: self.frame_no > after, timeout=timeout)
            return self.frame_no, self.preview_jpeg, self.full_jpeg

    def stop(self):
        self.running = False
        if self.cam is not None:
            self.cam.stop()


CAMERA = Camera()


class Handler(BaseHTTPRequestHandler):
    def _headers(self, code, ctype, length=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        if length is not None:
            self.send_header("Content-Length", str(length))
        self.end_headers()

    def _jpeg(self, which):
        _, prev, full = CAMERA.wait_frame(0)
        data = full if which == "full" else prev
        if not data:
            self._headers(503, "text/plain")
            self.wfile.write(b"camera not ready")
            return
        self._headers(200, "image/jpeg", len(data))
        self.wfile.write(data)

    def do_OPTIONS(self):
        self._headers(204, "text/plain")

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/health":
            body = json.dumps(
                {"ok": CAMERA.preview_jpeg is not None, "camera": CAMERA.name, "size": PHOTO_SIZE}
            ).encode()
            self._headers(200, "application/json", len(body))
            self.wfile.write(body)
        elif path == "/snapshot.jpg":
            self._jpeg("preview")
        elif path == "/photo.jpg":
            self._jpeg("full")
        elif path == "/stream.mjpg":
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            last = 0
            try:
                while CAMERA.running:
                    last, prev, _ = CAMERA.wait_frame(last)
                    if prev:
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n")
                        self.wfile.write(b"Content-Length: %d\r\n\r\n" % len(prev))
                        self.wfile.write(prev + b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass  # the page closed the preview
        else:
            self._headers(404, "text/plain")
            self.wfile.write(b"not found")

    def log_message(self, fmt, *args):
        pass  # keep the terminal quiet (one line per frame otherwise)


def main():
    CAMERA.start()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.daemon_threads = True

    def shutdown(*_):
        CAMERA.stop()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)
    print("Pre-registration camera (%s) ready on port %d." % (CAMERA.name, PORT))
    print("Test it in a browser: http://<this Pi's IP>:%d/stream.mjpg" % PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        shutdown()
    time.sleep(0.2)


main()
