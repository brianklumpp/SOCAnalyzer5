# syntax=docker/dockerfile:1
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system deps if needed later (kept minimal for now)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Copy project (keep paths so config.py can resolve PROJECT_ROOT correctly)
COPY . /app

# Ensure data dirs exist and are writable (can be mounted via volumes in compose)
RUN mkdir -p /app/data/output /app/data/json /app/data/logs

EXPOSE 8000

# Default command (can be overridden by compose)
CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]


