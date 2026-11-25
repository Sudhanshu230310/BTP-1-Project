#!/bin/bash
# ============================================================
#  BMW iDrive Gesture Control — Raspberry Pi Setup Script
#  Tested on: Raspberry Pi 4B / 5 (8GB RAM) | Pi OS 64-bit
#  Supports: IP Webcam (Wi-Fi) + Bluetooth Audio/Media
# ============================================================
set -e

echo "============================================================"
echo "   BMW iDrive Gesture Control — Raspberry Pi Setup"
echo "============================================================"

echo "[1/5] Installing system dependencies (OpenCV, Bluetooth, Audio)..."
sudo apt-get update -qq
sudo apt-get install -y \
    python3-pip python3-venv \
    libopencv-dev python3-opencv \
    libatlas-base-dev libhdf5-dev \
    bluez bluez-tools pulseaudio-utils playerctl dbus \
    git curl

echo "[2/5] Creating Python virtual environment..."
python3 -m venv venv --system-site-packages
source venv/bin/activate

echo "[3/5] Installing Python packages..."
pip install --upgrade pip wheel
pip install mediapipe || pip install mediapipe-rpi4
pip install opencv-python numpy

echo "[4/5] Checking Bluetooth & media tools..."
which bluetoothctl && echo "  bluetoothctl OK" || echo "  [WARN] bluetoothctl not found"
which playerctl && echo "  playerctl OK" || echo "  [WARN] playerctl not found"
which pactl && echo "  pactl OK" || echo "  [WARN] pactl not found"

echo "[5/5] Verifying Python imports..."
python3 - <<'EOF'
import cv2, mediapipe, numpy
print(f"  opencv-python : {cv2.__version__}")
print(f"  mediapipe     : {mediapipe.__version__}")
print(f"  numpy         : {numpy.__version__}")
print("  All imports OK!")
EOF

echo ""
echo "============================================================"
echo "  Setup complete!"
echo ""
echo "  1) Start IP Webcam on your phone (same Wi-Fi as Pi)"
echo "  2) Connect your Bluetooth speaker/device to the Pi"
echo "  3) Run:"
echo "       source venv/bin/activate"
echo "       python version4_2_pi.py --camera http://<PHONE_IP>:8080/video"
echo "     (Add --headless if running over SSH without a monitor)"
echo "============================================================"
