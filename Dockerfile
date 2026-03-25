### Multi-stage build:
### 1) Build frontend with Vite
### 2) Build Python backend image and copy static assets in

FROM node:20-bookworm-slim AS frontend-build
WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


FROM python:3.11-slim AS backend
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Install python deps
COPY pyproject.toml README.md LICENSE* ./
COPY src/ ./src/

RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
 && pip install --no-cache-dir .

# Copy built frontend into Flask static folder
COPY --from=frontend-build /app/src/web/static/ ./src/web/static/

ENV PORT=5001
EXPOSE 5001

# Production server (no auto-reloader)
CMD ["gunicorn", "-b", "0.0.0.0:5001", "--workers", "2", "--threads", "4", "--timeout", "180", "src.web.app:app"]

