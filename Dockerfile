# ── Persona AI Assistant — Docker ──
FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY app/ .

# Create logs directory
RUN mkdir -p logs

# Run
CMD ["python", "-m", "main"]

# Health check
HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
    CMD python -c "import motor.motor_asyncio; print('ok')" || exit 1
