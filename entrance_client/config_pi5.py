"""Entrance camera settings for the Raspberry Pi 5 (USB webcam at the evacuation center entrance).

setup_pi5.sh copies this file over config.py on the Pi. Edit the copy on the Pi if needed."""

# Where the FastAPI backend runs. On the server laptop itself, use 127.0.0.1.
# On the Raspberry Pi, use the laptop's static IP: "http://192.168.100.200:8000"
BACKEND_URL = "http://192.168.100.200:8000"

# Barangay official account the camera signs in with (test account).
USERNAME = "brgytest"
PASSWORD = "TestPass123!"  # noqa: S105

# The evacuation center this camera guards. 1 = Test Elementary School.
EVACUATION_CENTER_ID = 1

# Which camera watches the entrance:
#   0      = the first webcam (laptop built-in camera, or a Pi 4 with one USB webcam)
#   "usb"  = the first USB webcam. Use this on the Raspberry Pi 5, because the Camera
#            Module 3 (used for pre-registration) also shows up as a camera there.
CAMERA_INDEX = "usb"

# Face match strictness. 0.6 is the face_recognition default; lower is stricter.
MATCH_TOLERANCE = 0.6

# Do not check the same person in again within this many seconds.
CHECKIN_COOLDOWN_SECONDS = 300

# Reload enrolled faces (and who is already inside) this often, in seconds.
ENROLLED_FACES_REFRESH_SECONDS = 60

# Detection runs on a smaller copy of each frame for speed. 0.25 = quarter size (Pi).
# With a 1280x720 picture, 0.25 means faces are searched in a 320x180 copy.
# Raise to 0.35 or 0.5 to catch faces farther away (slower on the Pi).
FRAME_SCALE = 0.25

# True shows a window with boxes and names (needs a screen). False prints to the terminal only.
SHOW_PREVIEW = True

# Port where the live picture (with face boxes and names) is shared for the TV Mode page.
# 0 turns it off.
STREAM_PORT = 8081

# ---- Picture quality ----
# Size of the picture taken from the webcam. The UGREEN 2K webcam supports 1280x720 and
# 1920x1080. Larger = sharper and recognizes faces from farther away, but uses more CPU.
# Set both to 0 to use the webcam's default (640x480).
CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720
CAMERA_FPS = 30

# Width of the live picture sent to TV Mode, and its JPEG quality (1 to 100).
# Higher = sharper on the TV, but more network traffic.
STREAM_WIDTH = 1280
STREAM_QUALITY = 85
