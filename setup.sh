#!/usr/bin/env bash
# ============================================================================
# OpenClaw MeshCore - Setup Script
# Run on Hermes (.73) where the WIO Pro P1 Tracker is connected
# ============================================================================

set -e

echo "================================================"
echo "  OpenClaw MeshCore - Setup"
echo "================================================"

# Check Python version
PYTHON=$(command -v python3 || command -v python)
if [ -z "$PYTHON" ]; then
    echo "ERROR: Python 3.10+ is required but not found."
    exit 1
fi

PY_VERSION=$($PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "Python version: $PY_VERSION"

# Create virtual environment
echo ""
echo "[1/5] Creating virtual environment..."
$PYTHON -m venv .venv
source .venv/bin/activate

# Install dependencies
echo ""
echo "[2/5] Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Check for WIO Tracker
echo ""
echo "[3/5] Detecting MeshCore device..."
if ls /dev/ttyACM* 1>/dev/null 2>&1; then
    PORT=$(ls /dev/ttyACM* | head -1)
    echo "  Found: $PORT"
elif ls /dev/ttyUSB* 1>/dev/null 2>&1; then
    PORT=$(ls /dev/ttyUSB* | head -1)
    echo "  Found: $PORT"
else
    echo "  WARNING: No serial device detected."
    echo "  Make sure WIO Tracker is plugged in via USB."
    PORT="/dev/ttyACM0"
fi

# Set serial permissions
echo ""
echo "[4/5] Setting serial port permissions..."
if [ -e "$PORT" ]; then
    sudo chmod 666 "$PORT" 2>/dev/null || true
    # Add current user to dialout group for persistent access
    sudo usermod -a -G dialout $(whoami) 2>/dev/null || true
    echo "  Port $PORT is accessible."
fi

# Check Ollama
echo ""
echo "[5/5] Checking AI backends..."
if curl -s http://192.168.1.73:11434/api/tags >/dev/null 2>&1; then
    echo "  Ollama: ONLINE"
    # List available models
    MODELS=$(curl -s http://192.168.1.73:11434/api/tags | python3 -c "
import json, sys
data = json.load(sys.stdin)
for m in data.get('models', []):
    print(f'    - {m[\"name\"]}')
" 2>/dev/null || echo "    (could not list models)")
    echo "$MODELS"
else
    echo "  Ollama: OFFLINE (will use remote AI only)"
fi

if [ -n "$ANTHROPIC_API_KEY" ]; then
    echo "  Anthropic API key: SET"
else
    echo "  Anthropic API key: NOT SET"
    echo "    Set with: export ANTHROPIC_API_KEY='sk-ant-...'"
fi

echo ""
echo "================================================"
echo "  Setup complete!"
echo ""
echo "  To run:"
echo "    source .venv/bin/activate"
echo "    export ANTHROPIC_API_KEY='your-key-here'"
echo "    python openclaw_meshcore.py"
echo ""
echo "  Or with options:"
echo "    python openclaw_meshcore.py --port $PORT --prefer-local --debug"
echo "================================================"
