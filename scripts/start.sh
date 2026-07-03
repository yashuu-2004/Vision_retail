#!/bin/bash
# ============================================================================
# VisionRetail AI - One-shot reviewer startup
# ============================================================================
# Run with:    ./scripts/start.sh
# Brings up:   API, Dashboard, (optional Postgres)
# Then:        - API:      http://localhost:8000/docs
#              - Dashboard: http://localhost:8501
#              - Postgres:  localhost:5432
# ============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> VisionRetail AI - reviewer startup"

if [ ! -f .env ]; then
    echo "    No .env found — copying from .env.example"
    cp .env.example .env
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: docker is not installed.  Install Docker Desktop or docker-engine." >&2
    exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
    echo "ERROR: 'docker compose' plugin is not installed." >&2
    exit 1
fi

echo "==> Validating metadata for all stores"
python3 scripts/validate_metadata.py || {
    echo "    Metadata validation failed — see errors above." >&2
    exit 1
}

echo "==> Building images"
docker compose build

echo "==> Starting services"
docker compose up -d

echo "==> Waiting for API to become healthy"
for i in $(seq 1 30); do
    if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
        echo "    API is healthy after ${i}s"
        break
    fi
    sleep 1
done

echo
echo "==> Services running:"
docker compose ps

echo
echo "Endpoints:"
echo "  - API root:    http://localhost:8000"
echo "  - API docs:    http://localhost:8000/docs"
echo "  - Health:      http://localhost:8000/health"
echo "  - Stores:      http://localhost:8000/stores"
echo "  - Dashboard:   http://localhost:8501"
echo
echo "Run 'docker compose logs -f api' to follow API logs."
echo "Run 'docker compose down' to stop everything."
