#!/usr/bin/env bash
# One-command local run: builds the frontend and starts CometIQ on http://localhost:8000
#   ./run.sh            PostgreSQL (started with Docker if it is installed), like production
#   ./run.sh --sqlite   a local SQLite file instead (no Docker needed)
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] || cp .env.example .env
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r backend/requirements.txt
(cd frontend && npm install --no-audit --no-fund && npm run build)

PG_URL="postgresql+psycopg://cometiq:cometiq@localhost:5432/cometiq"
if [ "${1:-}" = "--sqlite" ]; then
  export DATABASE_URL="sqlite:///$(pwd)/backend/cometiq.db"
elif [ -z "${DATABASE_URL:-}" ]; then
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    echo "Starting PostgreSQL (docker compose service 'db')…"
    docker compose up -d db
    for _ in $(seq 1 30); do docker compose exec -T db pg_isready -U cometiq >/dev/null 2>&1 && break; sleep 1; done
    export DATABASE_URL="$PG_URL"
  else
    echo "Docker is not available: using SQLite for this run. Install Docker (or set DATABASE_URL) to develop on PostgreSQL."
    export DATABASE_URL="sqlite:///$(pwd)/backend/cometiq.db"
  fi
fi
echo "Database: ${DATABASE_URL%%@*}@…"
cd backend && exec ../.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
