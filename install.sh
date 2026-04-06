#!/usr/bin/env bash
# JARVIS installer — Arch Linux / CachyOS
set -e
JARVIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  JARVIS — Local AI Voice Assistant Installer"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── System packages ────────────────────────────────────
echo "[1/5] Installing system packages via pacman…"
sudo pacman -S --needed --noconfirm \
    python python-pip \
    portaudio \
    alsa-utils \
    espeak-ng \
    dunst \
    brightnessctl \
    pulseaudio-utils

# ── Ollama ─────────────────────────────────────────────
echo "[2/5] Installing Ollama…"
if ! command -v ollama &>/dev/null; then
    yay -S --needed --noconfirm ollama
fi
sudo systemctl enable --now ollama

echo "      Pulling models (this may take a while)…"
ollama pull llama3.2:3b
ollama pull qwen2.5:7b

# ── Whisper.cpp ────────────────────────────────────────
echo "[3/5] Installing whisper.cpp…"
if ! command -v whisper-cpp &>/dev/null; then
    yay -S --needed --noconfirm whisper-cpp
fi
# Download medium model weights
WHISPER_MODEL_DIR="${HOME}/.local/share/whisper"
mkdir -p "$WHISPER_MODEL_DIR"
if [ ! -f "$WHISPER_MODEL_DIR/ggml-medium.bin" ]; then
    echo "      Downloading Whisper medium model…"
    wget -q --show-progress \
        "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-medium.bin" \
        -O "$WHISPER_MODEL_DIR/ggml-medium.bin"
fi

# ── Piper TTS ──────────────────────────────────────────
echo "[4/5] Installing Piper TTS…"
pip install --user piper-tts

PIPER_MODEL_DIR="${HOME}/.local/share/piper"
mkdir -p "$PIPER_MODEL_DIR"
if [ ! -f "$PIPER_MODEL_DIR/en_US-lessac-high.onnx" ]; then
    echo "      Downloading Piper voice model…"
    wget -q --show-progress \
        "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/high/en_US-lessac-high.onnx" \
        -O "$PIPER_MODEL_DIR/en_US-lessac-high.onnx"
    wget -q --show-progress \
        "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/high/en_US-lessac-high.onnx.json" \
        -O "$PIPER_MODEL_DIR/en_US-lessac-high.onnx.json"
fi

# ── Python deps ────────────────────────────────────────
echo "[5/5] Installing Python dependencies…"
pip install --user \
    pyaudio \
    numpy \
    openWakeWord \
    requests

# ── i3 keybind hint ────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Add these lines to your ~/.config/i3/config:"
echo ""
echo "  # JARVIS toggle gaming mode"
echo "  bindsym \$mod+F12 exec python ${JARVIS_DIR}/jarvis.py --toggle-mode"
echo ""
echo "  # JARVIS autostart"
echo "  exec_always --no-startup-id python ${JARVIS_DIR}/jarvis.py &"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Installation complete! Run: python jarvis.py"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
