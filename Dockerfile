# House of Minds: FastAPI (API + static React build) on one port.
# Default: validated snapshot mode; no Databricks credentials or warehouse needed.
# Live Unity Catalog reads are optional: build with --build-arg WITH_DATABRICKS=true and set
# HOM_DATA_MODE=databricks plus server-side Databricks credentials. See docs/DEPLOYMENT.md.

# ---- 1. React static export ------------------------------------------------------------
FROM node:22-slim AS web
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build && rm -rf out/data   # raw exports are served only through the API

# ---- 2. FastAPI runtime ----------------------------------------------------------------
FROM python:3.12-slim
ARG WITH_DATABRICKS=false
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 \
    HOM_DATA_MODE=snapshot PORT=8000
WORKDIR /app
COPY requirements-web.txt requirements-databricks.txt ./
RUN if [ "$WITH_DATABRICKS" = "true" ]; then pip install -r requirements-databricks.txt; \
    else pip install -r requirements-web.txt; fi
COPY backend/ backend/
COPY config/ config/
COPY web/public/data/current/ web/public/data/current/
COPY web/public/data/sidecar/ web/public/data/sidecar/
COPY --from=web /app/web/out web/out
RUN useradd --create-home --uid 10001 app && chown -R app /app
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/api/v1/health',timeout=4)"
# Render (and most hosts) inject $PORT; bind on all interfaces.
CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
