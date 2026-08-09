# ─────────────────────────────────────────────────────────────
# Token-Sentry — Dockerfile
# Builds a lean production image for the FastAPI proxy server.
#
# Build:   docker build -t token-sentry .
# Run:     docker run -p 8000:8000 --env-file .env token-sentry
# ─────────────────────────────────────────────────────────────

# Use slim Python 3.11 — smaller image, same behaviour
FROM python:3.11-slim

# Set working directory inside the container
WORKDIR /app

# ── Install system dependencies ────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# ── Install dependencies first (Docker layer caching) ─────────
# Copy requirements before source code so this layer is only
# rebuilt when requirements.txt changes — not on every code edit
COPY requirements.txt .
RUN pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

# ── Copy application source code ──────────────────────────────
COPY src/ ./src/

# ── Create logs directory (app writes here at runtime) ────────
RUN mkdir -p logs

# ── Non-root user (security best practice) ────────────────────
# Running as root in a container is a security risk
RUN useradd --create-home appuser
RUN chown -R appuser:appuser /app
USER appuser

# ── Expose port ───────────────────────────────────────────────
EXPOSE 8000

# ── Health check ──────────────────────────────────────────────
# Docker will ping /health every 30s. If it fails 3 times,
# the container is marked "unhealthy" and can be auto-restarted.
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# ── Start command ─────────────────────────────────────────────
# Use 2 workers in production (adjust based on CPU cores)
# --host 0.0.0.0 = listen on all interfaces (required in containers)
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
