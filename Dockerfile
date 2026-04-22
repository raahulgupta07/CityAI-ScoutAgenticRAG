# ============================================================================
# Document Intelligence Agent — Single-Image Dockerfile
# ============================================================================
# Stage 1: Build SvelteKit frontend → static HTML/JS/CSS
# Stage 2: Python API + frontend static files in one container
# ============================================================================

# --- Stage 1: Build Frontend ---
FROM node:22-slim AS frontend-builder

WORKDIR /frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build
# Output: /frontend/build/ (static HTML/JS/CSS)

# --- Stage 2: Python API + Frontend ---
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# System dependencies (gcc for builds, poppler+fonts for PDF rendering)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev curl \
    poppler-utils \
    fonts-liberation fonts-dejavu-core fontconfig \
    && fc-cache -fv \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python dependencies (cached layer)
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY backend/ ./backend/

# Instance config (branding, persona, categories)
COPY instance.yaml ./instance.yaml

# Copy frontend build output
COPY --from=frontend-builder /frontend/build /app/static-frontend

# Copy widget
COPY backend/static/ ./backend/static/

# Data directories
RUN mkdir -p /data/pdfs /data/screenshots /data/uploads

# Entrypoint
COPY scripts/entrypoint.sh /app/scripts/entrypoint.sh
RUN chmod +x /app/scripts/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
