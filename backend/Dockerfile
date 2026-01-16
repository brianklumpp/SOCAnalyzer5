# syntax=docker/dockerfile:1
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system deps (including dnsutils for nslookup, netcat for port checking, and tesseract for OCR)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    dnsutils \
    netcat-openbsd \
    tesseract-ocr \
    tesseract-ocr-eng \
 && mkdir -p /etc/apt/keyrings \
 && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends docker-ce-cli \
 && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Copy project (keep paths so config.py can resolve PROJECT_ROOT correctly)
COPY backend/ /app/backend

# Ensure data dirs exist and are writable (can be mounted via volumes in compose)
RUN mkdir -p /app/data/output /app/data/json /app/data/logs /app/data/template

# Copy Excel template from host to image
COPY data/template/*.xlsx /app/data/template/

# Copy and set up entrypoint script
COPY backend/entrypoint.sh /app/entrypoint.sh
RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh

EXPOSE 8000

# Use entrypoint to configure DNS before starting app
ENTRYPOINT ["/app/entrypoint.sh"]

# Default command (can be overridden by compose)
CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]



