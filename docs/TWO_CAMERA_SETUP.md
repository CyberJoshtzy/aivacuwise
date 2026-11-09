# Ai-Vacuwise Two-Camera Setup (Raspberry Pi 5)

One Raspberry Pi 5 runs both cameras. The laptop server stays the center of the system.

| Camera | Connected to | Used for | Program on the Pi |
|---|---|---|---|
| Raspberry Pi Camera Module 3 | Pi 5 camera port (ribbon cable) | Pre-registration: left, front and right photos | `pi_camera/prereg_camera.py` (service, port 8080, starts at boot) |
| USB webcam | Pi 5 USB port | Entrance of the evacuation center: walk-through check-in | `entrance_client/recognize.py` (started by hand) |

## How the data moves

```
Camera Module 3 -> Pi 5 (prereg_camera.py, port 8080) -> Pre-Registration page in the browser
                -> laptop /faces/check and /faces/encode -> PostgreSQL (face reference record)

USB webcam -> Pi 5 (recognize.py: detects and matches faces against GET /evacuees/enrolled_faces)
           -> laptop POST /checkin (or a transfer) -> PostgreSQL -> live dashboard
```

Pre-registration faces are checked and encoded on the laptop. Entrance matching runs on the Pi 5
itself, so only small check-in requests travel over Wi-Fi, not video. The Pi downloads the
enrolled faces from the laptop every minute.

## What you need

1. Raspberry Pi 5 with Raspberry Pi OS (64-bit, Desktop) on a microSD card.
2. Camera Module 3 with a **Raspberry Pi 5 camera cable**. The Pi 5 camera port is smaller
   (22-pin) than the cable that comes with the Camera Module 3 (15-pin), so a Pi 5 cable
   (22-pin to 15-pin) is required.
3. USB webcam (the Rapoo webcam already used).
4. Official Raspberry Pi 5 power supply (5V, 5A USB-C). A weaker charger causes low-voltage
   warnings and can limit power to the USB webcam.
5. The Pi and the laptop on the same network (the Converge router, Wi-Fi or Ethernet).

## Step 1: Connect the hardware (Pi turned off)

1. Lift the latch of the camera port marked CAM/DISP 0, insert the narrow end of the Pi 5
   cable with the metal contacts facing the USB/Ethernet ports, and press the latch down.
2. Connect the other end to the Camera Module 3 the same way (contacts facing the lens board).
3. Plug the USB webcam into a blue USB 3 port.
4. Connect power. Wait about one minute for the Pi to start.

## Step 2: Find the Pi on the network (on the Pi)

Open a terminal on the Pi and run `hostname -I`. The first number is the Pi's address,
for example `192.168.100.50`. Write it down; the next steps call it `PI_IP`.

## Step 3: Copy the camera programs from the laptop (on the laptop)

```
cd ~/ai-vacuwise && git pull
ssh PI_USER@PI_IP "mkdir -p ~/ai-vacuwise-pi"
scp -r entrance_client pi_camera PI_USER@PI_IP:~/ai-vacuwise-pi/
```

Replace `PI_USER` with the Pi's username and `PI_IP` with its address.

## Step 4: Run the setup (on the Pi)

```
cd ~/ai-vacuwise-pi && bash pi_camera/setup_pi5.sh
```

It installs the camera and face recognition packages, sets the entrance camera to the USB
webcam and the laptop address, and starts the pre-registration camera service. It asks for
the Pi's password with visible typing. At the end it prints the Pi's address and checks the camera.

Check: `curl -s http://127.0.0.1:8080/health` on the Pi should show `"ok": true`.

## Step 5: Use the Camera Module 3 for pre-registration (any browser on the network)

1. Open `http://192.168.100.200:8000/static/app/preregister.html` and sign in.
2. Under **Camera**, choose **Raspberry Pi camera (Camera Module 3)** and type `http://PI_IP:8080`.
3. Click **Turn On Camera**. The live Pi camera picture appears; capture the three photos as usual.

The address is remembered by that browser. "This computer's webcam" is still available as a backup.
Because the camera is on the Pi, pre-registration no longer has to be done on the laptop itself.

## Step 6: Entrance camera (starts by itself)

The setup installs `ai-vacuwise-entrance-camera`, a background service that starts the USB
webcam recognizer whenever the Pi turns on. It reports to the laptop every 15 seconds, so the
Live Evacuation page and the Entrance Display show **Camera on** or **Camera off**.

- Watch it: `sudo journalctl -u ai-vacuwise-entrance-camera -f`
- Set the center it guards: `EVACUATION_CENTER_ID` in `entrance_client/config.py` on the Pi,
  then `sudo systemctl restart ai-vacuwise-entrance-camera`.
- To see the camera window for testing: `sudo systemctl stop ai-vacuwise-entrance-camera`,
  then `cd ~/ai-vacuwise-pi/entrance_client && python3 recognize.py` (press `q` to stop),
  then `sudo systemctl start ai-vacuwise-entrance-camera`.
- Only re-install the services (no package downloads): `bash pi_camera/install_services.sh`
- TV Mode (`tv.html`, the "Open TV Mode" button on Live Evacuation) shows the live webcam picture
  with green boxes and names for recognized evacuees. The Pi shares it on port 8081
  (`STREAM_PORT` in `entrance_client/config.py`, 0 turns it off); the page finds the address
  from the heartbeat, so nothing has to be typed.

## Troubleshooting

| Problem | Fix |
|---|---|
| `No Camera Module found` | Turn the Pi off, reseat both ends of the ribbon cable (contacts facing the right way, latches closed), check that it is the Pi 5 cable, start again. `rpicam-hello --list-cameras` should list `imx708`. |
| Page says it cannot reach the Pi camera | Check the address and port 8080, run `sudo systemctl status ai-vacuwise-prereg-camera` on the Pi, and make sure the Pi and laptop are on the same network. |
| Picture is upside down | Set `ROTATE_180 = True` at the top of `pi_camera/prereg_camera.py`, then `sudo systemctl restart ai-vacuwise-prereg-camera`. |
| `No USB webcam found` | Plug the webcam into another USB port and check `v4l2-ctl --list-devices`. |
| Entrance recognition is slow | Keep `FRAME_SCALE = 0.25`. If faces far from the camera are missed and speed is fine, try `0.35`. |
| Low-voltage warning | Use the official 5V 5A Pi 5 power supply. |
