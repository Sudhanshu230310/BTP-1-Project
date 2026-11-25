# BMW iDrive Gesture Control — Raspberry Pi + IP Webcam + Bluetooth

Control music playback and volume on a **Raspberry Pi (8 GB RAM)** using hand gestures captured from your **phone over Wi-Fi (IP Webcam)** and played through a **Bluetooth speaker / device** connected to the Pi.

---

## Architecture

```
[Phone: IP Webcam App] ──(Same Wi-Fi: http://<PHONE_IP>:8080/video)──▶ [Raspberry Pi: version4_2_pi.py]
                                                                                  │
                                                                    (Bluetooth A2DP + AVRCP / pactl / playerctl)
                                                                                  ▼
                                                                       [Bluetooth Speaker / Music]
```

---

## Step 1 — Push This Project to GitHub (from your Mac)

> **Important:** Make sure you initialize Git inside `Gesture-Driven-Media-Control-main` (so `venv/` is excluded via `.gitignore`).

```bash
cd ~/Desktop/Gesture-Driven-Media-Control-main

git init
git add .
git commit -m "Add Raspberry Pi IP Webcam + Bluetooth gesture control"
git branch -M main
git remote add origin https://github.com/<YOUR_USERNAME>/<YOUR_REPO_NAME>.git
git push -u origin main
```

---

## Step 2 — Set Up Your Phone (IP Webcam)

1. Connect your Android phone to the **same Wi-Fi network** as the Raspberry Pi.
2. Install **IP Webcam** from the Google Play Store.
3. Open IP Webcam → scroll down → tap **Start server**.
4. Note the IPv4 address shown on screen, e.g. `http://192.168.1.105:8080`.
   - The video stream URL is `http://192.168.1.105:8080/video`.

---

## Step 3 — Pair Your Bluetooth Speaker / Device on the Raspberry Pi

Run in the Raspberry Pi terminal (or use the desktop Bluetooth icon):

```bash
bluetoothctl
power on
agent on
scan on
# Wait until your Bluetooth speaker MAC appears (e.g. AA:BB:CC:DD:EE:FF)
pair AA:BB:CC:DD:EE:FF
trust AA:BB:CC:DD:EE:FF
connect AA:BB:CC:DD:EE:FF
quit
```

Verify Bluetooth audio sink is active:
```bash
pactl list short sinks
```
You should see a `bluez_output...` sink.

---

## Step 4 — Clone & Install on Raspberry Pi

```bash
git clone https://github.com/<YOUR_USERNAME>/<YOUR_REPO_NAME>.git ~/gesture-control
cd ~/gesture-control
chmod +x setup_pi.sh
./setup_pi.sh
```

---

## Step 5 — Run on Raspberry Pi

Start a music player on the Pi (e.g., Spotify, VLC, Chromium, Rhythmbox) outputting to your Bluetooth speaker, then run:

```bash
cd ~/gesture-control
source venv/bin/activate

# With monitor connected to Pi:
python version4_2_pi.py --camera http://192.168.1.105:8080/video

# Over SSH (no monitor connected):
python version4_2_pi.py --camera 192.168.1.105 --headless
```

> Tip: Passing `--camera 192.168.1.105` automatically expands to `http://192.168.1.105:8080/video`.

---

## Gesture Reference (3-Second Cooldown)

| Gesture | Action |
|---|---|
| ☝️ Index finger + **clockwise** rotation | Volume **UP** |
| ☝️ Index finger + **counter-clockwise** rotation | Volume **DOWN** |
| 👉 Long drag / swipe **right** | Next track |
| 👈 Long drag / swipe **left** | Previous track |
| 👉 Point index forward (push) | Play / Pause |
| ✌️ Two fingers (peace sign) | Mute / Unmute |
| ✋ Open palm | Cancel / Standby |

---

## Troubleshooting

- **Cannot open camera stream**: Confirm phone and Pi are on the same Wi-Fi, IP Webcam server is running, and test `http://<PHONE_IP>:8080/video` in Chromium on the Pi.
- **Volume not changing on Bluetooth speaker**: Run `pactl list short sinks` and set the Bluetooth sink as default: `pactl set-default-sink <SINK_NAME>`.
- **Next/Prev/Play-Pause not responding**: Make sure `playerctl status` shows your music player (e.g. `Playing` / `Paused`).
