"""BilisLikas 2.0: live face check for the Pre-Registration camera.

POST /faces/check  {image: small JPEG data URL, angle: left|front|right}
Returns {ok, code, message, box:[x,y,w,h] (0-1), yaw}. The page turns the oval green only when ok is true.

Checks, in order:
  no face / more than one face / face too small (too far) / too big (too close) / not centered /
  too dark / eyes covered (sunglasses, hand) / nose and mouth covered (face mask) /
  wrong head turn for the requested angle.
Runs on the laptop server with face_recognition (dlib), no internet needed.
"""

import base64
import io

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import auth

router = APIRouter()

TURN_MIN, TURN_MAX, FRONT_MAX = 0.12, 0.55, 0.10


class FrameIn(BaseModel):
    image: str
    angle: str | None = "front"


def _res(ok, code, message, box=None, yaw=None):
    return {"ok": ok, "code": code, "message": message, "box": box, "yaw": yaw}


def _skin_fraction(ycrcb, pts, pad=0):
    """Share of skin-coloured pixels inside the bounding box of the given landmark points."""
    h, w = ycrcb.shape[:2]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0, x1 = max(0, min(xs) - pad), min(w, max(xs) + pad)
    y0, y1 = max(0, min(ys) - pad), min(h, max(ys) + pad)
    if x1 - x0 < 3 or y1 - y0 < 3:
        return None, None
    roi = ycrcb[y0:y1, x0:x1].reshape(-1, 3).astype(float)
    cr, cb = roi[:, 1], roi[:, 2]
    skin = ((cr >= 133) & (cr <= 180) & (cb >= 75) & (cb <= 130)).mean()
    return float(skin), float(roi[:, 0].mean())


def _to_ycrcb(rgb):
    import numpy as np

    r, g, b = [rgb[..., i].astype(float) for i in range(3)]
    y = 0.299 * r + 0.587 * g + 0.114 * b
    cr = (r - y) * 0.713 + 128
    cb = (b - y) * 0.564 + 128
    return np.stack([y, cr, cb], axis=-1)


@router.post("/faces/check")
def faces_check(p: FrameIn, user=Depends(auth.get_current_user)):
    import numpy as np
    from PIL import Image

    try:
        import face_recognition
    except ImportError:
        raise HTTPException(  # noqa: B904
            status_code=503, detail="Face recognition is not installed on the server."
        )
    try:
        raw = p.image.split(",", 1)[1] if p.image.startswith("data:") else p.image
        img = Image.open(io.BytesIO(base64.b64decode(raw))).convert("RGB")
    except Exception:
        return _res(False, "unreadable", "Camera image could not be read.")
    if img.width > 480:
        img = img.resize((480, int(img.height * 480 / img.width)))
    arr = np.array(img)
    H, W = arr.shape[:2]

    locs = face_recognition.face_locations(arr, number_of_times_to_upsample=1, model="hog")
    if not locs:
        return _res(False, "none", "No full face found. Show the whole face: eyes, nose and mouth.")
    if len(locs) > 1:
        return _res(
            False, "many", "More than one face. Only the evacuee should be in front of the camera."
        )
    top, right, bottom, left = locs[0]
    fw, fh = right - left, bottom - top
    box = [round(left / W, 3), round(top / H, 3), round(fw / W, 3), round(fh / H, 3)]
    if fw < 0.18 * W:
        return _res(False, "far", "Move closer to the camera.", box)
    if fw > 0.62 * W:
        return _res(False, "close", "Move a little farther from the camera.", box)
    cx, cy = (left + right) / 2 / W, (top + bottom) / 2 / H
    if not (0.28 < cx < 0.72 and 0.22 < cy < 0.75):
        return _res(False, "center", "Move the face to the middle of the oval.", box)

    lm = face_recognition.face_landmarks(arr, face_locations=[locs[0]])
    if not lm:
        return _res(
            False, "none", "Face not clear. Show the whole face: eyes, nose and mouth.", box
        )
    lm = lm[0]
    ycc = _to_ycrcb(arr)
    face_y = ycc[top:bottom, left:right, 0].mean()
    if face_y < 55:
        return _res(False, "dark", "The face is too dark. Face the light or turn on a lamp.", box)

    eyes = lm.get("left_eye", []) + lm.get("right_eye", [])
    mouth = lm.get("top_lip", []) + lm.get("bottom_lip", [])
    nose = lm.get("nose_tip", []) + lm.get("nose_bridge", [])[-1:]
    cheeks_ref = [(left + fw // 6, top + fh // 2), (right - fw // 6, top + int(fh * 0.62))]
    pad = max(2, fw // 25)
    eye_skin, eye_y = _skin_fraction(ycc, eyes, pad)
    mouth_skin, _ = _skin_fraction(ycc, mouth + lm.get("chin", [])[6:11], pad)
    nose_skin, _ = _skin_fraction(ycc, nose, pad)
    cheek_skin, cheek_y = _skin_fraction(ycc, cheeks_ref, max(4, fw // 10))

    # Eyes covered: the eye area is much darker than the cheeks (sunglasses) or has no skin around it
    if (
        eye_y is not None
        and cheek_y
        and (eye_y < 0.45 * cheek_y or (eye_skin is not None and eye_skin < 0.08))
    ):
        return _res(
            False, "eyes", "The eyes are covered. Remove sunglasses or anything over the eyes.", box
        )
    # Nose and mouth covered: little skin colour where the nose and mouth should be (face mask, hand, cloth)
    if mouth_skin is not None and nose_skin is not None and mouth_skin < 0.25 and nose_skin < 0.35:
        return _res(
            False,
            "mask",
            "The nose and mouth are covered. Remove the face mask or anything over the mouth.",
            box,
        )
    if mouth_skin is not None and mouth_skin < 0.15:
        return _res(False, "mouth", "The mouth is covered. Show the whole face.", box)

    # Head turn: nose position compared with the middle of the eyes (camera image, not mirrored)
    le, re_ = lm.get("left_eye"), lm.get("right_eye")
    tip = lm.get("nose_tip")
    yaw = None
    if le and re_ and tip:
        lx = sum(x for x, _ in le) / len(le)
        rx = sum(x for x, _ in re_) / len(re_)
        nx = sum(x for x, _ in tip) / len(tip)
        eye_dist = abs(rx - lx) or 1
        yaw = round(
            (nx - (lx + rx) / 2) / eye_dist, 3
        )  # + : nose toward image right = person's LEFT
    angle = (p.angle or "front").lower()
    if yaw is not None:
        if angle == "front" and abs(yaw) > FRONT_MAX:
            return _res(False, "turn_front", "Look straight at the camera.", box, yaw)
        if angle == "left":
            if yaw < TURN_MIN:
                return _res(False, "turn_more", "Turn the head slightly to the LEFT.", box, yaw)
            if yaw > TURN_MAX:
                return _res(
                    False,
                    "turn_less",
                    "Too far. Turn back a little so both eyes stay visible.",
                    box,
                    yaw,
                )
        if angle == "right":
            if yaw > -TURN_MIN:
                return _res(False, "turn_more", "Turn the head slightly to the RIGHT.", box, yaw)
            if yaw < -TURN_MAX:
                return _res(
                    False,
                    "turn_less",
                    "Too far. Turn back a little so both eyes stay visible.",
                    box,
                    yaw,
                )
    return _res(True, "ok", "Face detected. Hold still and capture.", box, yaw)
