# Gesture-Driven Media Control System (Cross-Platform & Ultra-Smooth)

This project is a **touchless gesture-driven media control system** inspired by BMW's in-car gesture controls. It allows users to control system volume and media playback (Spotify, Apple Music, System Media) using intuitive hand gestures with zero lag and high-precision visual feedback.

---

## 🌟 Key Features

- **🌐 Full Cross-Platform Compatibility**:
  - **macOS**: Native AppleScript control for Spotify, Apple Music & system volume.
  - **Windows**: Native `pycaw` audio endpoint control & virtual media keys.
  - **Linux**: PulseAudio/PipeWire (`pactl`), ALSA (`amixer`), `playerctl` & `xdotool`.
  - Universal fallback via `pyautogui`.
- **⚡ Ultra-Smooth & Zero Lag**:
  - Asynchronous background worker thread for hardware audio/media calls.
  - Video stream runs at native 60+ FPS without subshell/process blocking stutter.
- **🎯 Precision Landmark & Angle Smoothing**:
  - Exponential Weighted Moving Average (EWMA) filter removes hand micro-jitter.
  - Wrap-around boundary handling (-180° to 180° continuous rollover) for hand rotation.
  - Deadzone filtering prevents volume jumps when holding hand still.
- **🏎️ BMW-Inspired Futuristic HUD**:
  - Semi-transparent glassmorphic UI cards.
  - Dynamic circular volume arc gauge with smooth lerp animation and color gradients.
  - Interactive touch zones with proximity scaling and cooldown countdown arcs.
  - Visual ripple wave effects on gesture activation.

---

## 🚀 Setup & Installation

1. **Clone the repository and navigate to the project directory:**
   ```bash
   git clone https://github.com/Sudhanshu230310/EC-AI-Frontend.git
   cd Gesture-Driven-Media-Control-main
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the gesture control system:**
   ```bash
   python version4_2.py
   ```

---

## 🎮 How To Use

| Gesture / Action | Result |
| :--- | :--- |
| **Rotate Hand** (Clockwise / Counter-Clockwise) | Smoothly adjust system volume up / down |
| **Hover Left Zone** (`|< PREV`) | Skip to previous track |
| **Hover Right Zone** (`NEXT >|`) | Skip to next track |
| **Hover Top Zone** or **Pinch Thumb & Index** | Toggle Play / Pause |
| **Key `Q` or `ESC`** | Quit application |
| **Key `M`** | Toggle Mute |
| **Key `R`** | Reset volume to 50% |
| **Key `H`** | Toggle HUD overlay |

---

## 🛠️ Tech Stack

- **Python 3.8+**
- **OpenCV**: Camera input and UI overlay rendering.
- **MediaPipe**: Real-time 3D hand tracking and landmark estimation.
- **NumPy**: Math operations and coordinate filtering.
- **Threading & Queues**: Asynchronous non-blocking command execution.

# BTP-1-Project
