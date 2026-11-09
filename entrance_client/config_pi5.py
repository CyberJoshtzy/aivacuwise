"""Entrance camera settings for the Raspberry Pi 5 (USB webcam at the evacuation center entrance).

setup_pi5.sh copies this file over config.py on the Pi. Edit the copy on the Pi if needed."""

# Where the FastAPI backend runs. On the server laptop itself, use 127.0.0.1.
# On the Raspberry Pi, use the laptop's static IP: "http://192.168.100.200:8000"
BACKEND_URL = "http://192.168.100.200:8000"

# Barangay official account the camera signs in with (test account).
USERNAME = "brgytest"
PASSWORD = "TestPass123!"  # noqa: S105

# The evacuation center this camera guards. 1 = Test Elementary School.
EVACUATION_CENTER_ID = 2

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

# Detection runs on a smaller copy of each frame for speed. 0.25 = quarter size (Pi),
# 0.5 = half size (laptop, better for faces farther away).
FRAME_SCALE = 0.25

# True shows a window with boxes and names (needs a screen). False prints to the terminal only.
SHOW_PREVIEW = True
