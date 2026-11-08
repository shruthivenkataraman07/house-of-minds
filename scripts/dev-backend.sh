#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
exec uv run uvicorn backend.main:app --reload --port "${BACKEND_PORT:-8000}"
