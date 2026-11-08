#!/usr/bin/env bash
# Reproducible install from lockfiles. Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")/.."

command -v uv >/dev/null || { echo "uv missing: brew install uv"; exit 1; }
command -v node >/dev/null || { echo "node missing: brew install node"; exit 1; }
if [[ "$(uname)" == "Darwin" ]] && ! brew list libomp >/dev/null 2>&1; then
  echo "LightGBM needs OpenMP on macOS: brew install libomp"; exit 1
fi

uv sync --frozen
(cd frontend && npm ci && npx playwright install chromium)
[[ -f .env ]] || cp .env.example .env
echo "Setup complete. Run scripts/verify.sh"
