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
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    xvfb \
 && rm -rf /var/lib/apt/lists/*

# Install python deps
COPY pyproject.toml README.md LICENSE* ./
COPY src/ ./src/

RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir . \
    && python -m playwright install-deps \
    && python - <<'PY'
import io, json, zipfile, pathlib
import requests

from camoufox import pkgman

install_dir = pathlib.Path(pkgman.INSTALL_DIR)
install_dir.mkdir(parents=True, exist_ok=True)

# Pinned Camoufox asset (matches the installed version on the dev machine).
# camoufox-135.0.1-beta.24-lin.x86_64.zip
url = "https://github.com/daijro/camoufox/releases/download/v135.0.1-beta.24/camoufox-135.0.1-beta.24-lin.x86_64.zip"
version = "135.0.1"
release = "beta.24"

resp = requests.get(url, timeout=120)
resp.raise_for_status()

z = zipfile.ZipFile(io.BytesIO(resp.content))
z.extractall(str(install_dir))

# Write version metadata expected by camoufox pkgman.
(install_dir / "version.json").write_text(json.dumps({"version": version, "release": release}))

# Ensure executable permissions where relevant.
import os
for p in install_dir.rglob("*"):
    try:
        if p.is_file():
            os.chmod(p, 0o755)
    except Exception:
        pass
print(f"Camoufox installed into {install_dir}")
PY

# Copy built frontend into Flask static folder
COPY --from=frontend-build /app/src/web/static/ ./src/web/static/

ENV PORT=5001
# Camoufox on Linux: native headless often breaks in Docker; 'virtual' uses Xvfb (installed above).
ENV SCRAPER_HEADLESS=virtual
EXPOSE 5001

# Production server (no auto-reloader). Many hosts set PORT at runtime.
# IMPORTANT: keep workers=1 and threads=1 because scrape job status is stored in-process memory,
# and concurrent scraping can easily exhaust limited container resources.
# timeout=0 disables the worker silence limit so long scrapes are not killed mid-run when
# polling pauses or the browser is slow (see Gunicorn docs for trade-offs).
CMD ["sh", "-c", "exec gunicorn -b 0.0.0.0:${PORT:-5001} --workers 1 --threads 1 --timeout 0 src.web.app:app"]

