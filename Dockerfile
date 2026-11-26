# ── 1. Build the React frontend ───────────────────────────────────────
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ── 2. Python API that also serves the built frontend ─────────────────
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=web /web/dist /app/frontend/dist
RUN useradd -m cometiq && chown -R cometiq /app
USER cometiq
EXPOSE 8000
# uvicorn reads WEB_CONCURRENCY as the number of worker processes (about one per CPU core; see DEPLOY.md)
ENV WEB_CONCURRENCY=2
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
