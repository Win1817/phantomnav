FROM python:3.12-slim

# ── System deps ───────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Dependencies (cached layer) ───────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── App code ─────────────────────────────────────────────────
COPY . .

# ── Non-root user ─────────────────────────────────────────────
RUN adduser --disabled-password --gecos "" phantom \
  && chown -R phantom:phantom /app
USER phantom

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

CMD ["python", "-m", "uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--loop", "uvloop", \
     "--no-access-log"]
