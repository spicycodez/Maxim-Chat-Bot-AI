#!/bin/bash
# ── VPS Quick Deploy Script (Ubuntu/Debian) ──
set -e

APP_DIR="$HOME/Maxim-Chat-Bot-AI"
SERVICE_FILE="/etc/systemd/system/persona-ai.service"

if [ ! -f "$APP_DIR/app/main.py" ]; then
    echo "ERROR: main.py not found at $APP_DIR/app/main.py"
    echo "Clone your repo first:"
    echo "  git clone https://github.com/spicycodez/Maxim-Chat-Bot-AI.git $APP_DIR"
    exit 1
fi

# 1. Install Python 3.12 if needed
if ! python3.12 --version 2>/dev/null; then
    echo "Installing Python 3.12..."
    sudo apt update && sudo apt install -y software-properties-common
    sudo add-apt-repository -y ppa:deadsnakes/ppa
    sudo apt update && sudo apt install -y python3.12 python3.12-venv python3-pip
fi

# 2. Create venv
if [ ! -d "$APP_DIR/venv" ]; then
    echo "Creating virtual environment..."
    python3.12 -m venv "$APP_DIR/venv"
fi

# 3. Install deps
echo "Installing dependencies..."
source "$APP_DIR/venv/bin/activate"
pip install --upgrade pip
pip install -r "$APP_DIR/requirements.txt"

# 4. Create logs dir
mkdir -p "$APP_DIR/app/logs"

# 5. Check .env
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    echo ""
    echo "==============================="
    echo "  .env created from template!"
    echo "  EDIT IT NOW with your keys:"
    echo "  nano $APP_DIR/.env"
    echo "==============================="
    exit 1
fi

# 6. Install systemd service
echo "Installing systemd service..."
sed -i "s|/root/Maxim-Chat-Bot-AI|$APP_DIR|g" "$APP_DIR/persona-ai.service"
sed -i "s|/usr/bin/python3|$APP_DIR/venv/bin/python|g" "$APP_DIR/persona-ai.service"
sudo cp "$APP_DIR/persona-ai.service" "$SERVICE_FILE"
sudo systemctl daemon-reload
sudo systemctl enable persona-ai

# 7. Start
echo "Starting bot..."
sudo systemctl start persona-ai
sleep 3
sudo systemctl status persona-ai --no-pager

echo ""
echo "==============================="
echo "  Bot deployed!"
echo ""
echo "  Commands:"
echo "  sudo systemctl start persona-ai    # Start"
echo "  sudo systemctl stop persona-ai     # Stop"
echo "  sudo systemctl restart persona-ai  # Restart"
echo "  journalctl -u persona-ai -f         # Live logs"
echo "==============================="
