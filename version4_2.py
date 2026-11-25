"""
BMW iDrive Gesture Control System (Authentic, Ultra-Smooth & Cross-Platform)
Compatible with macOS, Windows, and Linux.

Authentic BMW Gesture Commands:
1. ☝️ Index Finger Pointing + Rotate:
   - Clockwise Rotation -> Volume UP 🔊
   - Counter-Clockwise Rotation -> Volume DOWN 🔉
2. 🔄 Hand Swipe:
   - Swipe Right 👉 -> Next Song / Track ⏭️
   - Swipe Left 👈 -> Previous Song / Track ⏮️
3. 👉 Point Index Finger Forward / Push Tap:
   - Select / Play / Pause ⏯️
4. ✌️ Two Fingers Pointing Forward (Peace / V Sign):
   - Mute / Unmute Toggle 🔇 (BMW Programmable Shortcut)
5. ✋ Open Palm Facing Camera:
   - Return / Pause / Mute Function ✋
"""

import collections
import cv2
import math
import numpy as np
import os
import platform
import queue
import subprocess
import threading
import time
import warnings
warnings.filterwarnings('ignore')
import mediapipe as mp


class CrossPlatformAudioMediaController:
    """
    Asynchronous, non-blocking audio & media playback controller.
    Executes commands in a dedicated background worker thread for zero frame drops.
    """
    def __init__(self):
        self.os_type = platform.system()  # 'Darwin', 'Windows', 'Linux'
        self.cmd_queue = queue.Queue(maxsize=10)
        self.last_volume = -1
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        
        # Windows pycaw initialization
        self.pycaw_vol = None
        if self.os_type == 'Windows':
            try:
                from ctypes import cast, POINTER
                from comtypes import CLSCTX_ALL
                from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                devices = AudioUtilities.GetSpeakers()
                interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                self.pycaw_vol = cast(interface, POINTER(IAudioEndpointVolume))
            except Exception:
                self.pycaw_vol = None

        self.pyautogui_available = False
        try:
            import pyautogui
            self.pyautogui = pyautogui
            self.pyautogui_available = True
        except ImportError:
            self.pyautogui = None

    def set_volume(self, volume_percent):
        vol = max(0, min(100, int(volume_percent)))
        if vol == self.last_volume:
            return
        self.last_volume = vol
        
        # Keep queue lean by removing older volume requests
        new_queue = queue.Queue(maxsize=10)
        try:
            while not self.cmd_queue.empty():
                item = self.cmd_queue.get_nowait()
                if item[0] != 'volume':
                    new_queue.put_nowait(item)
        except queue.Empty:
            pass
        self.cmd_queue = new_queue
        
        try:
            self.cmd_queue.put_nowait(('volume', vol))
        except queue.Full:
            pass

    def trigger_media_action(self, action):
        """action: 'next', 'previous', 'playpause', 'mute'"""
        try:
            self.cmd_queue.put_nowait(('media', action))
        except queue.Full:
            pass

    def _worker_loop(self):
        while True:
            try:
                task_type, val = self.cmd_queue.get(timeout=0.5)
                if task_type == 'volume':
                    self._change_volume(val)
                elif task_type == 'media':
                    self._change_media(val)
                self.cmd_queue.task_done()
            except queue.Empty:
                continue
            except Exception:
                pass

    def _change_volume(self, volume):
        if self.os_type == 'Darwin':
            subprocess.run(
                ["osascript", "-e", f"set volume output volume {volume}"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        elif self.os_type == 'Windows':
            if self.pycaw_vol:
                try:
                    self.pycaw_vol.SetMasterVolumeLevelScalar(volume / 100.0, None)
                except Exception:
                    self._win_fallback_volume(volume)
            else:
                self._win_fallback_volume(volume)
        elif self.os_type == 'Linux':
            res = subprocess.run(
                ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{volume}%"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            if res.returncode != 0:
                subprocess.run(
                    ["amixer", "sset", "Master", f"{volume}%"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )

    def _win_fallback_volume(self, volume):
        try:
            ps_cmd = (
                "$wsh = New-Object -ComObject WScript.Shell; "
                "1..50 | % { $wsh.SendKeys([char]174) }; "
                f"1..{int(volume/2)} | % {{ $wsh.SendKeys([char]175) }}"
            )
            subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def _change_media(self, action):
        if self.os_type == 'Darwin':
            cmd_map = {'previous': 'previous track', 'next': 'next track', 'playpause': 'playpause'}
            if action in cmd_map:
                script_cmd = cmd_map[action]
                res = subprocess.run(
                    ["osascript", "-e", f'tell application "Spotify" to {script_cmd}'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                if res.returncode != 0:
                    res2 = subprocess.run(
                        ["osascript", "-e", f'tell application "Music" to {script_cmd}'],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    if res2.returncode != 0 and self.pyautogui_available:
                        key = 'prevtrack' if action == 'previous' else 'nexttrack' if action == 'next' else 'playpause'
                        self.pyautogui.press(key)
        elif self.os_type == 'Windows':
            try:
                import ctypes
                vk_map = {'previous': 0x91, 'next': 0x90, 'playpause': 0x8D}
                if action in vk_map:
                    vk = vk_map[action]
                    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
            except Exception:
                if self.pyautogui_available and action in ['previous', 'next', 'playpause']:
                    key = 'prevtrack' if action == 'previous' else 'nexttrack' if action == 'next' else 'playpause'
                    self.pyautogui.press(key)
        elif self.os_type == 'Linux':
            cmd_map = {'previous': 'previous', 'next': 'next', 'playpause': 'play-pause'}
            if action in cmd_map:
                res = subprocess.run(["playerctl", cmd_map[action]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if res.returncode != 0:
                    key_map = {'previous': 'XF86AudioPrev', 'next': 'XF86AudioNext', 'playpause': 'XF86AudioPlay'}
                    res2 = subprocess.run(["xdotool", "key", key_map[action]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if res2.returncode != 0 and self.pyautogui_available:
                        key = 'prevtrack' if action == 'previous' else 'nexttrack' if action == 'next' else 'playpause'
                        self.pyautogui.press(key)


class LandmarkSmoother:
    """Exponential Weighted Moving Average (EWMA) filter for hand landmark coordinates."""
    def __init__(self, alpha=0.35):
        self.alpha = alpha
        self.smooth_pts = {}

    def filter(self, pt_id, raw_pt):
        if pt_id not in self.smooth_pts:
            self.smooth_pts[pt_id] = raw_pt
            return raw_pt
        prev_x, prev_y = self.smooth_pts[pt_id]
        curr_x, curr_y = raw_pt
        sm_x = self.alpha * curr_x + (1 - self.alpha) * prev_x
        sm_y = self.alpha * curr_y + (1 - self.alpha) * prev_y
        self.smooth_pts[pt_id] = (sm_x, sm_y)
        return (sm_x, sm_y)

    def reset(self):
        self.smooth_pts.clear()


class SwipeTracker:
    """Tracks hand wrist horizontal position buffer to detect left and right swipes."""
    def __init__(self, buffer_size=8, min_swipe_distance=110, max_duration=0.5):
        self.buffer = collections.deque(maxlen=buffer_size)
        self.min_swipe_distance = min_swipe_distance
        self.max_duration = max_duration

    def update(self, wrist_x, curr_time):
        self.buffer.append((wrist_x, curr_time))

    def detect_swipe(self):
        if len(self.buffer) < 4:
            return None
        start_x, start_t = self.buffer[0]
        end_x, end_t = self.buffer[-1]
        dt = end_t - start_t
        dx = end_x - start_x

        if 0.05 <= dt <= self.max_duration:
            if dx > self.min_swipe_distance:
                self.buffer.clear()
                return 'right'  # Swipe Right -> Next Track
            elif dx < -self.min_swipe_distance:
                self.buffer.clear()
                return 'left'   # Swipe Left -> Previous Track
        return None

    def clear(self):
        self.buffer.clear()


class VisualEffect:
    """Expanding animation ripples for activated BMW gestures."""
    def __init__(self, x, y, color=(0, 255, 255), label=""):
        self.x = int(x)
        self.y = int(y)
        self.color = color
        self.label = label
        self.radius = 25
        self.max_radius = 110
        self.alpha = 1.0

    def update(self):
        self.radius += 5
        self.alpha = max(0.0, 1.0 - (self.radius / self.max_radius))
        return self.radius < self.max_radius


def detect_extended_fingers(landmarks, w, h):
    """
    Evaluates finger extension state for all 5 fingers.
    Returns: [thumb_extended, index_extended, middle_extended, ring_extended, pinky_extended]
    """
    wrist = (landmarks[0].x * w, landmarks[0].y * h)
    
    def dist(p1, p2):
        return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

    tips = [4, 8, 12, 16, 20]
    pips = [2, 6, 10, 14, 18]

    # Thumb extension
    thumb_tip = (landmarks[4].x * w, landmarks[4].y * h)
    index_mcp = (landmarks[5].x * w, landmarks[5].y * h)
    thumb_ext = dist(thumb_tip, index_mcp) > dist((landmarks[3].x * w, landmarks[3].y * h), index_mcp) * 1.15

    extended = [thumb_ext]

    # Index, Middle, Ring, Pinky extensions
    for i in range(1, 5):
        tip = (landmarks[tips[i]].x * w, landmarks[tips[i]].y * h)
        pip = (landmarks[pips[i]].x * w, landmarks[pips[i]].y * h)
        extended.append(dist(tip, wrist) > dist(pip, wrist) * 1.18)

    return extended


def calculate_angle(x1, y1, x2, y2):
    return math.degrees(math.atan2(y2 - y1, x2 - x1))


def draw_glass_card(frame, pt1, pt2, color=(20, 24, 30), alpha=0.65):
    """Draws semi-transparent BMW iDrive glassmorphic card."""
    overlay = frame.copy()
    cv2.rectangle(overlay, pt1, pt2, color, -1)
    cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)
    cv2.rectangle(frame, pt1, pt2, (60, 80, 110), 1)


def draw_glowing_circle(frame, center, radius, color, thickness=2, glow_alpha=0.35):
    """Draws circle with soft outer aura."""
    overlay = frame.copy()
    cv2.circle(overlay, center, radius + 7, color, thickness + 4)
    cv2.addWeighted(overlay, glow_alpha, frame, 1 - glow_alpha, 0, frame)
    cv2.circle(frame, center, radius, color, thickness)


def main():
    # Initialize MediaPipe Hands
    mp_hands = mp.solutions.hands
    mp_draw = mp.solutions.drawing_utils
    hands = mp_hands.Hands(
        min_detection_confidence=0.75,
        min_tracking_confidence=0.65,
        max_num_hands=1
    )

    # Camera Setup
    cap = cv2.VideoCapture(0)
    width_cam, height_cam = 960, 540
    cap.set(3, width_cam)
    cap.set(4, height_cam)

    # Audio & Media Controller
    audio_ctrl = CrossPlatformAudioMediaController()
    os_name = audio_ctrl.os_type

    # Control Parameters
    volume = 50.0
    display_volume = 50.0
    audio_ctrl.set_volume(int(volume))

    # Gesture Trackers
    previous_angle = None
    rotation_sensitivity = 0.45  # Volume % per degree turn
    angle_deadzone = 0.7  # Degrees to filter trembling

    swipe_tracker = SwipeTracker(buffer_size=12, min_swipe_distance=220, max_duration=0.8)
    cooldown_time = 1.4  # Cooldown between media trigger actions
    last_action_time = {'swipe': 0, 'playpause': 0, 'mute': 0}

    # Global cross-gesture cooldown (2 sec lock after ANY gesture fires)
    GESTURE_COOLDOWN = 2.0
    last_gesture_time = 0.0   # Timestamp of the last fired gesture
    last_gesture_type = None  # Track which gesture type is active

    smoother = LandmarkSmoother(alpha=0.4)
    ripples = []
    show_hud = True
    is_muted = False
    saved_volume = 50.0

    # FPS Calculation
    fps_time = time.time()
    fps = 0.0

    print("==========================================================")
    print("      BMW iDrive Gesture Control System (Official)        ")
    print("----------------------------------------------------------")
    print(" ☝️ Index Finger + Rotate Clockwise    -> Volume UP 🔊     ")
    print(" ☝️ Index Finger + Rotate Counter-CW   -> Volume DOWN 🔉   ")
    print(" 🔄 Swipe Hand Right 👉                -> Next Track ⏭️    ")
    print(" 🔄 Swipe Hand Left 👈                 -> Previous Track ⏮️ ")
    print(" 👉 Point Index Forward / Tap          -> Play / Pause ⏯️  ")
    print(" ✌️ Two Fingers Forward (Peace Sign)   -> Mute Toggle 🔇   ")
    print(" ✋ Open Palm                          -> Cancel / Return  ")
    print("----------------------------------------------------------")
    print(" Controls: 'Q'/ESC: Quit | 'M': Mute | 'R': Reset | 'H': HUD")
    print("==========================================================")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Calculate FPS
        curr_time = time.time()
        fps = 0.9 * fps + 0.1 * (1.0 / max(0.001, curr_time - fps_time))
        fps_time = curr_time

        # Mirror video feed for intuitive user interaction
        frame = cv2.flip(frame, 1)
        h, w, _ = frame.shape

        # Process MediaPipe Hand Tracking
        image_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = hands.process(image_rgb)

        gesture_title = "IDLE - STANDBY"
        gesture_icon = "✋"
        active_gesture = None

        if results.multi_hand_landmarks:
            hand_landmarks = results.multi_hand_landmarks[0]
            landmarks = hand_landmarks.landmark

            # Draw hand skeleton overlay
            mp_draw.draw_landmarks(
                frame, hand_landmarks, mp_hands.HAND_CONNECTIONS,
                mp_draw.DrawingSpec(color=(0, 220, 255), thickness=2, circle_radius=3),
                mp_draw.DrawingSpec(color=(255, 120, 0), thickness=2)
            )

            # Retrieve key landmarks
            wrist_raw = landmarks[mp_hands.HandLandmark.WRIST]
            index_tip_raw = landmarks[mp_hands.HandLandmark.INDEX_FINGER_TIP]
            middle_tip_raw = landmarks[mp_hands.HandLandmark.MIDDLE_FINGER_TIP]

            # Convert to smoothed pixel coordinates
            wrist_pt = smoother.filter(0, (wrist_raw.x * w, wrist_raw.y * h))
            index_tip_pt = smoother.filter(8, (index_tip_raw.x * w, index_tip_raw.y * h))
            middle_tip_pt = smoother.filter(12, (middle_tip_raw.x * w, middle_tip_raw.y * h))

            wx, wy = wrist_pt
            ix, iy = index_tip_pt

            # Evaluate Finger Extension States
            # [thumb, index, middle, ring, pinky]
            ext = detect_extended_fingers(landmarks, w, h)
            thumb_ext, index_ext, middle_ext, ring_ext, pinky_ext = ext

            # Update Swipe Position Buffer
            swipe_tracker.update(wx, curr_time)
            detected_swipe = swipe_tracker.detect_swipe()

            # Helper: check whether global cross-gesture cooldown has expired.
            # Volume rotation is a continuous gesture — allowed to keep running when
            # it was already the active gesture.  Every other gesture is discrete
            # (fires once) so it needs a full 2-second rest even from itself.
            def gesture_allowed(gtype):
                if gtype == 'volume':
                    # Volume: OK if volume was already active, OR cooldown expired
                    return (last_gesture_type == 'volume' or
                            curr_time - last_gesture_time >= GESTURE_COOLDOWN)
                else:
                    # Discrete gestures: always need full cooldown after ANY gesture
                    return curr_time - last_gesture_time >= GESTURE_COOLDOWN

            # ----------------------------------------------------
            # BMW GESTURE 1: 🔄 SWIPE HAND RIGHT / LEFT
            # ----------------------------------------------------
            if (detected_swipe and
                    curr_time - last_action_time['swipe'] >= cooldown_time and
                    gesture_allowed('swipe')):
                if detected_swipe == 'right':
                    audio_ctrl.trigger_media_action('next')
                    last_action_time['swipe'] = curr_time
                    last_gesture_time = curr_time
                    last_gesture_type = 'swipe'
                    ripples.append(VisualEffect(w // 2 + 100, h // 2, (0, 255, 150), "NEXT TRACK ⏭️"))
                    print("[BMW Gesture] Swipe Right -> Next Track ⏭️")
                    gesture_title = "SWIPE RIGHT - NEXT TRACK"
                    gesture_icon = "👉"
                elif detected_swipe == 'left':
                    audio_ctrl.trigger_media_action('previous')
                    last_action_time['swipe'] = curr_time
                    last_gesture_time = curr_time
                    last_gesture_type = 'swipe'
                    ripples.append(VisualEffect(w // 2 - 100, h // 2, (0, 180, 255), "PREVIOUS TRACK ⏮️"))
                    print("[BMW Gesture] Swipe Left -> Previous Track ⏮️")
                    gesture_title = "SWIPE LEFT - PREVIOUS TRACK"
                    gesture_icon = "👈"

            # ----------------------------------------------------
            # BMW GESTURE 2: ✌️ TWO FINGERS FORWARD (MUTE / SHORTCUT)
            # Index & Middle Extended, Ring & Pinky Folded
            # ----------------------------------------------------
            elif index_ext and middle_ext and (not ring_ext) and (not pinky_ext):
                gesture_title = "TWO FINGERS - MUTE SHORTCUT"
                gesture_icon = "✌️"
                draw_glowing_circle(frame, (int(ix), int(iy)), 12, (0, 255, 255), 3)
                draw_glowing_circle(frame, (int(middle_tip_pt[0]), int(middle_tip_pt[1])), 12, (0, 255, 255), 3)

                if (curr_time - last_action_time['mute'] >= cooldown_time and
                        gesture_allowed('mute')):
                    is_muted = not is_muted
                    if is_muted:
                        saved_volume = volume
                        volume = 0.0
                    else:
                        volume = saved_volume
                    audio_ctrl.set_volume(int(volume))
                    last_action_time['mute'] = curr_time
                    last_gesture_time = curr_time
                    last_gesture_type = 'mute'
                    ripples.append(VisualEffect(int(ix), int(iy), (255, 0, 150), "MUTE TOGGLE 🔇"))
                    print(f"[BMW Gesture] Two Fingers -> Mute Toggle ({'MUTED' if is_muted else 'UNMUTED'})")

                previous_angle = None

            # ----------------------------------------------------
            # BMW GESTURE 3: ✋ OPEN PALM
            # All 5 Fingers Extended
            # ----------------------------------------------------
            elif index_ext and middle_ext and ring_ext and pinky_ext:
                gesture_title = "OPEN PALM - STANDBY / CANCEL"
                gesture_icon = "✋"
                draw_glowing_circle(frame, (int(wx), int(wy)), 30, (255, 200, 0), 2)
                previous_angle = None

            # ----------------------------------------------------
            # BMW GESTURE 4: ☝️ INDEX FINGER POINTING + ROTATE (VOLUME)
            # Index Extended Only (or Index & Thumb)
            # Blocked for GESTURE_COOLDOWN seconds after any other gesture fires.
            # ----------------------------------------------------
            elif index_ext and (not middle_ext) and (not ring_ext) and (not pinky_ext):
                current_angle = calculate_angle(wx, wy, ix, iy)

                # Draw Pointer Target Aura
                draw_glowing_circle(frame, (int(ix), int(iy)), 14, (0, 220, 255), 2)
                cv2.line(frame, (int(wx), int(wy)), (int(ix), int(iy)), (0, 220, 255), 2, cv2.LINE_AA)

                if gesture_allowed('volume'):
                    if previous_angle is not None:
                        angle_diff = current_angle - previous_angle

                        # Continuous wrap-around boundary protection
                        if angle_diff > 180:
                            angle_diff -= 360
                        elif angle_diff < -180:
                            angle_diff += 360

                        # Apply deadzone filter to remove trembling
                        if abs(angle_diff) >= angle_deadzone:
                            volume += angle_diff * rotation_sensitivity
                            volume = max(0.0, min(100.0, volume))
                            audio_ctrl.set_volume(int(volume))
                            # Mark volume as the active gesture on first real movement
                            if last_gesture_type != 'volume':
                                last_gesture_time = curr_time
                                last_gesture_type = 'volume'

                            rot_dir = "CLOCKWISE 🔊" if angle_diff > 0 else "COUNTER-CW 🔉"
                            gesture_title = f"INDEX ROTATE - {rot_dir} ({int(volume)}%)"
                            gesture_icon = "☝️"

                    previous_angle = current_angle
                else:
                    # Still in cooldown — show a "cooling down" label instead of acting
                    remaining = GESTURE_COOLDOWN - (curr_time - last_gesture_time)
                    gesture_title = f"COOLDOWN ({remaining:.1f}s)"
                    gesture_icon = "⏳"
                    previous_angle = None

            # ----------------------------------------------------
            # BMW GESTURE 5: 👉 POINT / TAP FORWARD (PLAY / PAUSE)
            # Index Pointing Forward Quick Push
            # ----------------------------------------------------
            elif (index_ext and (not middle_ext) and
                    curr_time - last_action_time['playpause'] >= cooldown_time and
                    gesture_allowed('playpause')):
                # Detect forward Z-depth motion or tap
                index_z = landmarks[8].z
                if index_z < -0.12:  # Finger pushed towards camera
                    audio_ctrl.trigger_media_action('playpause')
                    last_action_time['playpause'] = curr_time
                    last_gesture_time = curr_time
                    last_gesture_type = 'playpause'
                    ripples.append(VisualEffect(int(ix), int(iy), (255, 255, 0), "PLAY / PAUSE ⏯️"))
                    print("[BMW Gesture] Point / Push -> Play/Pause ⏯️")
                    gesture_title = "POINT PUSH - PLAY / PAUSE"
                    gesture_icon = "👉"
                previous_angle = None

            else:
                previous_angle = None

        else:
            previous_angle = None
            smoother.reset()
            swipe_tracker.clear()

        # Smooth volume gauge interpolation
        display_volume += 0.25 * (volume - display_volume)

        # ----------------------------------------------------
        # RENDER BMW iDrive GLASSMORPHISM HUD OVERLAY
        # ----------------------------------------------------
        if show_hud:
            # Active Visual Ripples
            ripples = [r for r in ripples if r.update()]
            for r in ripples:
                overlay = frame.copy()
                cv2.circle(overlay, (r.x, r.y), r.radius, r.color, 3)
                cv2.addWeighted(overlay, r.alpha, frame, 1 - r.alpha, 0, frame)
                if r.label:
                    cv2.putText(frame, r.label, (r.x - 60, r.y - r.radius - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, r.color, 2, cv2.LINE_AA)

            # Top Header Bar - BMW iDrive Glass Card
            draw_glass_card(frame, (15, 15), (w - 15, 75), (15, 22, 35), 0.75)
            cv2.putText(frame, "BMW iDrive GESTURE CONTROL", (30, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.putText(frame, f"OS: {os_name}", (370, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 220, 255), 2, cv2.LINE_AA)
            cv2.putText(frame, f"FPS: {int(fps)}", (w - 110, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180, 220, 255), 2, cv2.LINE_AA)

            # Sub-header Status Text
            cv2.putText(frame, f"{gesture_icon} {gesture_title}", (30, 67), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 255, 200), 1, cv2.LINE_AA)

            # ----------------------------------------------------
            # BMW GESTURE HELP GUIDE CARD (Bottom Left)
            # ----------------------------------------------------
            draw_glass_card(frame, (15, h - 165), (360, h - 15), (15, 22, 35), 0.75)
            cv2.putText(frame, "BMW GESTURE GUIDE", (28, h - 142), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 220, 255), 2, cv2.LINE_AA)
            cv2.putText(frame, "☝️ Rotate Index Finger : Volume Up/Down", (28, h - 120), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (220, 230, 240), 1, cv2.LINE_AA)
            cv2.putText(frame, "🔄 Swipe Right / Left   : Next / Prev Track", (28, h - 98), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (220, 230, 240), 1, cv2.LINE_AA)
            cv2.putText(frame, "👉 Point Push Forward   : Play / Pause", (28, h - 76), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (220, 230, 240), 1, cv2.LINE_AA)
            cv2.putText(frame, "✌️ Two Fingers Forward  : Mute Shortcut", (28, h - 54), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (220, 230, 240), 1, cv2.LINE_AA)
            cv2.putText(frame, "✋ Open Palm            : Cancel / Return", (28, h - 32), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (220, 230, 240), 1, cv2.LINE_AA)

            # ----------------------------------------------------
            # BMW CIRCULAR VOLUME DIAL GAUGE (Bottom Right)
            # ----------------------------------------------------
            gauge_center = (w - 85, h - 85)
            gauge_radius = 55

            # Outer ring track (135 deg to 405 deg)
            cv2.ellipse(frame, gauge_center, (gauge_radius, gauge_radius), 0, 135, 405, (40, 50, 68), 9, cv2.LINE_AA)

            # Dynamic Volume Fill Sweep
            vol_sweep = int(270 * (display_volume / 100.0))
            if vol_sweep > 0:
                if display_volume < 40:
                    vol_color = (255, 220, 0)
                elif display_volume < 75:
                    vol_color = (0, 255, 130)
                elif display_volume < 90:
                    vol_color = (0, 170, 255)
                else:
                    vol_color = (0, 60, 255)

                cv2.ellipse(frame, gauge_center, (gauge_radius, gauge_radius), 0, 135, 135 + vol_sweep, vol_color, 9, cv2.LINE_AA)

            # Percentage Text
            vol_str = f"{int(display_volume)}%" if not is_muted else "MUTED"
            text_color = (255, 255, 255) if not is_muted else (0, 100, 255)
            text_size, _ = cv2.getTextSize(vol_str, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            tx_offset = gauge_center[0] - text_size[0] // 2
            ty_offset = gauge_center[1] + text_size[1] // 2
            cv2.putText(frame, vol_str, (tx_offset, ty_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, text_color, 2, cv2.LINE_AA)
            cv2.putText(frame, "VOLUME", (gauge_center[0] - 28, gauge_center[1] + 34), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (180, 200, 220), 1, cv2.LINE_AA)

        # Show Output Window
        cv2.imshow("BMW iDrive Gesture Control (Cross-Platform)", frame)

        # Keyboard Controls
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == 27:  # Q or ESC
            break
        elif key == ord('m'):  # Toggle Mute
            is_muted = not is_muted
            volume = 0.0 if is_muted else 50.0
            audio_ctrl.set_volume(int(volume))
        elif key == ord('r'):  # Reset Volume
            volume = 50.0
            is_muted = False
            audio_ctrl.set_volume(50)
        elif key == ord('h'):  # Toggle HUD
            show_hud = not show_hud

    # Cleanup
    cap.release()
    cv2.destroyAllWindows()
    print("Application closed gracefully.")


if __name__ == '__main__':
    main()
