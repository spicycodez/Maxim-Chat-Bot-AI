#!/bin/bash
# ── VPS Quick Deploy Script ──
set -e

echo "🚀 Deploying Persona AI Assistant..."

# Check .env
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "⚠️  .env not found. Copied .env.example → .env"
    echo "   Edit .env with your credentials before running!"
    exit 1
fi

# Install deps
cd app
pip install -r requirements.txt

# Create logs dir
mkdir -p logs

echo "✅ Dependencies installed."
echo "Run: cd app && python main.py"
