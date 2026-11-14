#!/usr/bin/env bash
# One-command local run (no Docker): builds the frontend and starts CometIQ on http://localhost:8000
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] || cp .env.example .env
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r backend/requirements.txt
(cd frontend && npm install --no-audit --no-fund && npm run build)
cd backend && exec ../.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
