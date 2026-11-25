"""
BMW iDrive Gesture Control System — Raspberry Pi + IP Webcam + Bluetooth Edition
=================================================================================
Designed for Raspberry Pi 4 / 5 (64-bit OS, 4-8 GB RAM):
  • Phone on same Wi-Fi running "IP Webcam" streams video to Raspberry Pi.
  • Bluetooth speaker / headphones / phone connected to Raspberry Pi plays music.
  • 3-second global cooldown after any gesture so gestures never overlap.

Usage:
  # Phone IP Webcam (full URL or just the phone IP)
  python version4_2_pi.py --camera http://192.168.1.105:8080/video
  python version4_2_pi.py --camera 192.168.1.105

  # Run headless over SSH (no monitor attached to Pi)
  python version4_2_pi.py --camera 192.168.1.105 --headless

  # USB / CSI camera fallback
  python version4_2_pi.py --camera 0

Gesture Commands:
  ☝️  Index Finger + Rotate Clockwise   -> Volume UP
  ☝️  Index Finger + Rotate Counter-CW  -> Volume DOWN
  🔄  Long Swipe Hand Right             -> Next Track
  🔄  Long Swipe Hand Left              -> Previous Track
  👉  Point Index Forward / Push Tap    -> Play / Pause
  ✌️  Two Fingers (Peace Sign)          -> Mute Toggle
  ✋  Open Palm                         -> Cancel / Standby
"""

import argparse
import collections
import math
import os
import platform
import queue
import subprocess
import threading
import time
import warnings

warnings.filterwarnings("ignore")

import cv2
import mediapipe as mp


def normalize_camera_source(src):
    """
    Accepts:
      - '0', '1' -> integer USB camera index
      - '192.168.1.105' -> 'http://192.168.1.105:8080/video'
      - 'http://192.168.1.105:8080' -> 'http://192.168.1.105:8080/video'
      - 'http://192.168.1.105:8080/video' -> unchanged
    """
    s = str(src).strip()
    if s.isdigit():
        return int(s)
    if not s.startswith(("http://", "https://", "rtsp://")):
        s = f"http://{s}"
    if s.startswith(("http://", "https://")) and s.count("/") == 2:
        # No path provided; append default IP Webcam port/path if needed
        host_part = s.split("://", 1)[1]
        if ":" not in host_part:
            s = f"{s}:8080"
        s = f"{s}/video"
    elif s.startswith(("http://", "https://")) and s.endswith("/"):
        s = f"{s}video"
    return s


# ─────────────────────────────────────────────────────────────────────────────
# Threaded Frame Capture (prevents Wi-Fi / IP Webcam buffering lag)
# ─────────────────────────────────────────────────────────────────────────────
class ThreadedCapture:
    def __init__(self, src, width=640, height=480):
        self.src = normalize_camera_source(src)
        self.width = width
        self.height = height
        self.cap = None
        self.frame = None
        self.ret = False
        self.lock = threading.Lock()
        self.running = False
        self._thread = None
        self._open()

    def _open(self):
        self.cap = cv2.VideoCapture(self.src)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open camera source: {self.src}")
        for _ in range(3):
            self.ret, self.frame = self.cap.read()

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()
        return self

    def _reader(self):
        consecutive_failures = 0
        while self.running:
            ret, frame = self.cap.read()
            if ret and frame is not None:
                consecutive_failures = 0
                with self.lock:
                    self.ret = True
                    self.frame = frame
            else:
                consecutive_failures += 1
                with self.lock:
                    self.ret = False
                # Reconnect automatically if Wi-Fi stream stalls
                if consecutive_failures >= 30:
                    consecutive_failures = 0
                    try:
                        self.cap.release()
                        time.sleep(1.0)
                        self._open()
                    except Exception:
                        time.sleep(1.0)
                else:
                    time.sleep(0.02)

    def read(self):
        with self.lock:
            return self.ret, (self.frame.copy() if self.frame is not None else None)

    def stop(self):
        self.running = False
        if self.cap:
            self.cap.release()


# ─────────────────────────────────────────────────────────────────────────────
# Bluetooth-Aware Audio & Media Controller (Raspberry Pi / Linux + macOS)
# ─────────────────────────────────────────────────────────────────────────────
class BluetoothAudioMediaController:
    """
    Non-blocking controller executed on a background thread.
    On Raspberry Pi OS (PipeWire / PulseAudio + BlueZ):
      - Volume: targets active Bluetooth sink (bluez_*) or @DEFAULT_SINK@,
                with wpctl & amixer fallbacks.
      - Media : uses playerctl (Spotify/VLC/Chromium/mpris-proxy), with
                BlueZ AVRCP D-Bus fallback for connected Bluetooth devices.
    """

    def __init__(self):
        self.os_type = platform.system()
        self.cmd_queue = queue.Queue(maxsize=10)
        self.last_vol = -1
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def set_volume(self, vol_pct):
        vol = max(0, min(100, int(vol_pct)))
        if vol == self.last_vol:
            return
        self.last_vol = vol
        fresh = queue.Queue(maxsize=10)
        try:
            while not self.cmd_queue.empty():
                item = self.cmd_queue.get_nowait()
                if item[0] != "volume":
                    fresh.put_nowait(item)
        except queue.Empty:
            pass
        self.cmd_queue = fresh
        try:
            self.cmd_queue.put_nowait(("volume", vol))
        except queue.Full:
            pass

    def trigger(self, action):
        try:
            self.cmd_queue.put_nowait(("media", action))
        except queue.Full:
            pass

    def _worker(self):
        while True:
            try:
                kind, val = self.cmd_queue.get(timeout=0.5)
                if kind == "volume":
                    self._set_vol(val)
                elif kind == "media":
                    self._media(val)
                self.cmd_queue.task_done()
            except queue.Empty:
                continue
            except Exception:
                pass

    def _get_bluetooth_sink(self):
        """Returns the first active BlueZ sink name from pactl if available."""
        try:
            res = subprocess.run(
                ["pactl", "list", "short", "sinks"],
                capture_output=True, text=True, timeout=1.5
            )
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    parts = line.split("\t")
                    if len(parts) >= 2 and "bluez" in parts[1].lower():
                        return parts[1]
        except Exception:
            pass
        return None

    def _set_vol(self, vol):
        if self.os_type == "Linux":
            bt_sink = self._get_bluetooth_sink()
            sink_target = bt_sink if bt_sink else "@DEFAULT_SINK@"
            r = subprocess.run(
                ["pactl", "set-sink-volume", sink_target, f"{vol}%"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            if r.returncode != 0:
                # PipeWire WirePlumber fallback (Pi OS Bookworm)
                r2 = subprocess.run(
                    ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{vol / 100.0:.2f}"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                if r2.returncode != 0:
                    subprocess.run(
                        ["amixer", "sset", "Master", f"{vol}%"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
        elif self.os_type == "Darwin":
            subprocess.run(
                ["osascript", "-e", f"set volume output volume {vol}"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )

    def _media(self, action):
        if self.os_type == "Linux":
            pctl_cmd = {
                "previous": "previous",
                "next": "next",
                "playpause": "play-pause",
            }.get(action)
            if pctl_cmd:
                r = subprocess.run(
                    ["playerctl", pctl_cmd],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                if r.returncode != 0:
                    self._bluez_avrcp_fallback(action)
        elif self.os_type == "Darwin":
            cmd = {
                "previous": "previous track",
                "next": "next track",
                "playpause": "playpause",
            }.get(action)
            if cmd:
                subprocess.run(
                    ["osascript", "-e", f'tell application "Spotify" to {cmd}'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )

    def _bluez_avrcp_fallback(self, action):
        """
        Fallback for Bluetooth AVRCP via D-Bus when playerctl has no active MPRIS player.
        Searches org.bluez for a MediaPlayer1 object and sends Play/Pause/Next/Previous.
        """
        method_map = {"next": "Next", "previous": "Previous", "playpause": "Pause"}
        method = method_map.get(action)
        if not method:
            return
        try:
            intro = subprocess.run(
                [
                    "dbus-send", "--system", "--print-reply",
                    "--dest=org.bluez", "/", "org.freedesktop.DBus.ObjectManager.GetManagedObjects"
                ],
                capture_output=True, text=True, timeout=1.5
            )
            if intro.returncode != 0:
                return
            for line in intro.stdout.splitlines():
                if "/player" in line and "object path" in line:
                    path = line.split('"')[1]
                    subprocess.run(
                        [
                            "dbus-send", "--system", "--type=method_call",
                            "--dest=org.bluez", path, f"org.bluez.MediaPlayer1.{method}"
                        ],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    break
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Tracking & Visual Helpers
# ─────────────────────────────────────────────────────────────────────────────
class LandmarkSmoother:
    """Exponential Weighted Moving Average for hand landmark coordinates."""

    def __init__(self, alpha=0.35):
        self.alpha = alpha
        self.pts = {}

    def filter(self, pid, raw):
        if pid not in self.pts:
            self.pts[pid] = raw
            return raw
        px, py = self.pts[pid]
        cx, cy = raw
        sx = self.alpha * cx + (1 - self.alpha) * px
        sy = self.alpha * cy + (1 - self.alpha) * py
        self.pts[pid] = (sx, sy)
        return (sx, sy)

    def reset(self):
        self.pts.clear()


class SwipeTracker:
    """Tracks wrist X-position to detect long left/right swipes."""

    def __init__(self, buffer_size=12, min_dist=160, max_dur=0.8):
        self.buf = collections.deque(maxlen=buffer_size)
        self.min_dist = min_dist
        self.max_dur = max_dur

    def update(self, x, t):
        self.buf.append((x, t))

    def detect(self):
        if len(self.buf) < 4:
            return None
        sx, st = self.buf[0]
        ex, et = self.buf[-1]
        dt, dx = et - st, ex - sx
        if 0.05 <= dt <= self.max_dur:
            if dx > self.min_dist:
                self.buf.clear()
                return "right"
            elif dx < -self.min_dist:
                self.buf.clear()
                return "left"
        return None

    def clear(self):
        self.buf.clear()


class Ripple:
    """Expanding ring animation for gesture feedback."""

    def __init__(self, x, y, color=(0, 255, 255), label=""):
        self.x, self.y = int(x), int(y)
        self.color, self.label = color, label
        self.radius, self.max_r = 25, 110
        self.alpha = 1.0

    def update(self):
        self.radius += 5
        self.alpha = max(0.0, 1.0 - self.radius / self.max_r)
        return self.radius < self.max_r


def extended_fingers(lm, w, h):
    def d(a, b):
        return math.hypot(a[0] - b[0], a[1] - b[1])

    def pt(i):
        return (lm[i].x * w, lm[i].y * h)

    wrist = pt(0)
    thumb = d(pt(4), pt(5)) > d(pt(3), pt(5)) * 1.15
    fingers = [thumb]
    for tip, pip in [(8, 6), (12, 10), (16, 14), (20, 18)]:
        fingers.append(d(pt(tip), wrist) > d(pt(pip), wrist) * 1.18)
    return fingers


def calc_angle(x1, y1, x2, y2):
    return math.degrees(math.atan2(y2 - y1, x2 - x1))


def glass_card(frame, p1, p2, color=(20, 24, 30), a=0.65):
    ov = frame.copy()
    cv2.rectangle(ov, p1, p2, color, -1)
    cv2.addWeighted(ov, a, frame, 1 - a, 0, frame)
    cv2.rectangle(frame, p1, p2, (60, 80, 110), 1)


def glow_circle(frame, center, r, color, t=2, ga=0.35):
    ov = frame.copy()
    cv2.circle(ov, center, r + 7, color, t + 4)
    cv2.addWeighted(ov, ga, frame, 1 - ga, 0, frame)
    cv2.circle(frame, center, r, color, t)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="BMW iDrive Gesture Control — Raspberry Pi Edition")
    parser.add_argument(
        "--camera",
        default="0",
        help="IP Webcam URL (e.g. http://192.168.1.105:8080/video or just 192.168.1.105) or USB index (0)",
    )
    parser.add_argument("--width", type=int, default=640, help="Frame width (default 640)")
    parser.add_argument("--height", type=int, default=480, help="Frame height (default 480)")
    parser.add_argument("--flip", type=int, default=1, help="1=mirror (default), 0=none, -1=both")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run without OpenCV GUI window (useful over SSH)",
    )
    args = parser.parse_args()

    # Automatically enable headless on Linux if no display server is available
    has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    headless = args.headless or (platform.system() == "Linux" and not has_display)

    resolved_src = normalize_camera_source(args.camera)

    print("=" * 62)
    print("   BMW iDrive Gesture Control — Raspberry Pi + Bluetooth")
    print("-" * 62)
    print(f"   Camera source : {resolved_src}")
    print(f"   Resolution    : {args.width}x{args.height}")
    print(f"   Mode          : {'Headless (SSH)' if headless else 'GUI Window'}")
    print(f"   Platform      : {platform.system()} {platform.machine()}")
    print("-" * 62)
    print("   ☝️  Rotate Index Finger   -> Volume Up / Down")
    print("   🔄  Long Swipe Right/Left -> Next / Previous Track")
    print("   👉  Point Push Forward    -> Play / Pause")
    print("   ✌️  Two Fingers (Peace)   -> Mute Toggle")
    print("   ✋  Open Palm             -> Standby / Cancel")
    print("   ⏳  Cooldown              -> 3.0s global lock after gesture")
    print("=" * 62)

    print("[INFO] Connecting to camera stream...")
    try:
        cap = ThreadedCapture(resolved_src, args.width, args.height).start()
    except RuntimeError as e:
        print(f"[ERROR] {e}")
        print("[HINT] Make sure phone & Pi are on the same Wi-Fi and IP Webcam server is started.")
        print("[HINT] Example: python version4_2_pi.py --camera http://192.168.1.105:8080/video")
        return

    for _ in range(30):
        ret, frame = cap.read()
        if ret and frame is not None:
            break
        time.sleep(0.1)
    else:
        print("[ERROR] No frames received. Verify the IP Webcam URL in a browser first.")
        cap.stop()
        return
    print("[INFO] Camera stream connected!")

    mp_hands = mp.solutions.hands
    mp_draw = mp.solutions.drawing_utils
    hands = mp_hands.Hands(
        model_complexity=0,
        min_detection_confidence=0.70,
        min_tracking_confidence=0.60,
        max_num_hands=1,
    )

    audio = BluetoothAudioMediaController()
    volume = 50.0
    display_volume = 50.0
    audio.set_volume(50)

    prev_angle = None
    rot_sensitivity = 0.45
    angle_dead = 0.7

    # Scale swipe distance proportionally to frame width (~25% of frame width)
    min_swipe_px = max(120, int(args.width * 0.25))
    swiper = SwipeTracker(buffer_size=12, min_dist=min_swipe_px, max_dur=0.8)
    smoother = LandmarkSmoother(alpha=0.4)
    ripples = []
    show_hud = True
    is_muted = False
    saved_vol = 50.0

    COOLDOWN = 3.0
    last_gest_time = 0.0
    last_gest_type = None

    fps_time = time.time()
    fps = 0.0

    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                time.sleep(0.03)
                continue

            curr_time = time.time()
            fps = 0.9 * fps + 0.1 / max(0.001, curr_time - fps_time)
            fps_time = curr_time

            if args.flip != 0:
                frame = cv2.flip(frame, args.flip)
            h, w = frame.shape[:2]

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = hands.process(rgb)

            gesture_title = "IDLE - STANDBY"
            gesture_icon = "✋"
            cooldown_expired = (curr_time - last_gest_time >= COOLDOWN)

            if results.multi_hand_landmarks:
                lm_set = results.multi_hand_landmarks[0]
                lm = lm_set.landmark

                if not headless and show_hud:
                    mp_draw.draw_landmarks(
                        frame,
                        lm_set,
                        mp_hands.HAND_CONNECTIONS,
                        mp_draw.DrawingSpec(color=(0, 220, 255), thickness=2, circle_radius=3),
                        mp_draw.DrawingSpec(color=(255, 120, 0), thickness=2),
                    )

                wrist = smoother.filter(0, (lm[0].x * w, lm[0].y * h))
                ix_pt = smoother.filter(8, (lm[8].x * w, lm[8].y * h))
                mi_pt = smoother.filter(12, (lm[12].x * w, lm[12].y * h))
                wx, wy = wrist
                ix, iy = ix_pt

                ext = extended_fingers(lm, w, h)
                _, index_ext, middle_ext, ring_ext, pinky_ext = ext

                swiper.update(wx, curr_time)
                swipe = swiper.detect()

                if not cooldown_expired:
                    remaining = COOLDOWN - (curr_time - last_gest_time)
                    gesture_title = f"COOLDOWN - WAIT ({remaining:.1f}s)"
                    gesture_icon = "⏳"
                    prev_angle = None
                else:
                    if swipe == "right":
                        audio.trigger("next")
                        last_gest_time = curr_time
                        last_gest_type = "swipe_right"
                        ripples.append(Ripple(w // 2 + 80, h // 2, (0, 255, 150), "NEXT TRACK"))
                        print("[Gesture] Swipe Right -> Next Track")
                        gesture_title = "SWIPE RIGHT - NEXT TRACK"
                        gesture_icon = "👉"
                    elif swipe == "left":
                        audio.trigger("previous")
                        last_gest_time = curr_time
                        last_gest_type = "swipe_left"
                        ripples.append(Ripple(w // 2 - 80, h // 2, (0, 180, 255), "PREV TRACK"))
                        print("[Gesture] Swipe Left -> Previous Track")
                        gesture_title = "SWIPE LEFT - PREVIOUS TRACK"
                        gesture_icon = "👈"
                    elif index_ext and middle_ext and (not ring_ext) and (not pinky_ext):
                        gesture_title = "TWO FINGERS - MUTE TOGGLE"
                        gesture_icon = "✌️"
                        if not headless:
                            glow_circle(frame, (int(ix), int(iy)), 12, (0, 255, 255), 3)
                            glow_circle(frame, (int(mi_pt[0]), int(mi_pt[1])), 12, (0, 255, 255), 3)
                        is_muted = not is_muted
                        if is_muted:
                            saved_vol = volume
                            volume = 0.0
                        else:
                            volume = saved_vol
                        audio.set_volume(int(volume))
                        last_gest_time = curr_time
                        last_gest_type = "mute"
                        ripples.append(Ripple(int(ix), int(iy), (255, 0, 150), "MUTE TOGGLE"))
                        print(f"[Gesture] Mute -> {'MUTED' if is_muted else 'UNMUTED'}")
                        prev_angle = None
                    elif index_ext and middle_ext and ring_ext and pinky_ext:
                        gesture_title = "OPEN PALM - STANDBY"
                        gesture_icon = "✋"
                        if not headless:
                            glow_circle(frame, (int(wx), int(wy)), 30, (255, 200, 0), 2)
                        prev_angle = None
                    elif index_ext and (not middle_ext) and (not ring_ext) and (not pinky_ext):
                        cur_ang = calc_angle(wx, wy, ix, iy)
                        if not headless:
                            glow_circle(frame, (int(ix), int(iy)), 14, (0, 220, 255), 2)
                            cv2.line(frame, (int(wx), int(wy)), (int(ix), int(iy)), (0, 220, 255), 2, cv2.LINE_AA)

                        if prev_angle is not None:
                            da = cur_ang - prev_angle
                            if da > 180:
                                da -= 360
                            elif da < -180:
                                da += 360
                            if abs(da) >= angle_dead:
                                volume += da * rot_sensitivity
                                volume = max(0.0, min(100.0, volume))
                                audio.set_volume(int(volume))
                                if last_gest_type != "volume":
                                    last_gest_time = curr_time
                                    last_gest_type = "volume"
                                rot_dir = "UP" if da > 0 else "DOWN"
                                gesture_title = f"VOLUME {rot_dir} ({int(volume)}%)"
                                gesture_icon = "☝️"
                        prev_angle = cur_ang
                    elif index_ext and (not middle_ext):
                        if lm[8].z < -0.12:
                            audio.trigger("playpause")
                            last_gest_time = curr_time
                            last_gest_type = "playpause"
                            ripples.append(Ripple(int(ix), int(iy), (255, 255, 0), "PLAY / PAUSE"))
                            print("[Gesture] Point Push -> Play/Pause")
                            gesture_title = "POINT PUSH - PLAY / PAUSE"
                            gesture_icon = "👉"
                        prev_angle = None
                    else:
                        prev_angle = None
            else:
                prev_angle = None
                smoother.reset()
                swiper.clear()

            display_volume += 0.25 * (volume - display_volume)

            if not headless:
                if show_hud:
                    ripples = [r for r in ripples if r.update()]
                    for r in ripples:
                        ov = frame.copy()
                        cv2.circle(ov, (r.x, r.y), r.radius, r.color, 3)
                        cv2.addWeighted(ov, r.alpha, frame, 1 - r.alpha, 0, frame)
                        if r.label:
                            cv2.putText(
                                frame, r.label, (r.x - 60, r.y - r.radius - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, r.color, 2, cv2.LINE_AA
                            )

                    glass_card(frame, (10, 10), (w - 10, 65), (15, 22, 35), 0.75)
                    cv2.putText(
                        frame, "BMW iDrive | Pi + IPWebcam + BT",
                        (20, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA
                    )
                    cv2.putText(
                        frame, f"FPS: {int(fps)}",
                        (w - 95, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 220, 255), 2, cv2.LINE_AA
                    )
                    cv2.putText(
                        frame, f"{gesture_title}",
                        (20, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 255, 200), 1, cv2.LINE_AA
                    )

                    gc = (w - 65, h - 65)
                    gr = 45
                    cv2.ellipse(frame, gc, (gr, gr), 0, 135, 405, (40, 50, 68), 8, cv2.LINE_AA)
                    sweep = int(270 * display_volume / 100.0)
                    if sweep > 0:
                        vc = (
                            (255, 220, 0) if display_volume < 40 else
                            (0, 255, 130) if display_volume < 75 else
                            (0, 170, 255) if display_volume < 90 else (0, 60, 255)
                        )
                        cv2.ellipse(frame, gc, (gr, gr), 0, 135, 135 + sweep, vc, 8, cv2.LINE_AA)
                    vol_str = f"{int(display_volume)}%" if not is_muted else "MUTED"
                    tc = (255, 255, 255) if not is_muted else (0, 100, 255)
                    ts, _ = cv2.getTextSize(vol_str, cv2.FONT_HERSHEY_SIMPLEX, 0.52, 2)
                    cv2.putText(
                        frame, vol_str, (gc[0] - ts[0] // 2, gc[1] + ts[1] // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.52, tc, 2, cv2.LINE_AA
                    )

                cv2.imshow("BMW iDrive — Raspberry Pi Edition", frame)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    break
                elif key == ord("h"):
                    show_hud = not show_hud
                elif key == ord("r"):
                    volume = 50.0
                    is_muted = False
                    audio.set_volume(50)
                elif key == ord("m"):
                    is_muted = not is_muted
                    volume = 0.0 if is_muted else saved_vol
                    audio.set_volume(int(volume))
    except KeyboardInterrupt:
        print("\n[INFO] Interrupted by user.")
    finally:
        cap.stop()
        if not headless:
            cv2.destroyAllWindows()
        print("Application closed gracefully.")


if __name__ == "__main__":
    main()
