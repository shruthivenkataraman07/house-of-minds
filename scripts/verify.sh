#!/usr/bin/env bash
# Runs every toolchain check. Makes no paid API calls and starts no Databricks compute.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== Python: lint, types, tests =="
uv run ruff check .
uv run mypy backend config analytics pipelines evidence models optimization
uv run pytest tests

echo "== Step 1 data pipeline (requires scripts/fetch_data.sh) =="
if [[ -f data/raw/dashboard-royale/data/manifest.json ]]; then
  uv run python scripts/run_step1.py > /dev/null && echo "pipeline OK"
else
  echo "dataset not downloaded; skipped"
fi

echo "== Frontend: lint, typecheck, unit tests, build =="
(cd frontend && npm run lint && npm run typecheck && npm test && npm run build)

echo "== Databricks (read-only) =="
if command -v databricks >/dev/null; then
  databricks current-user me -p "${DATABRICKS_PROFILE:-HOUSE_OF_MINDS}" >/dev/null \
    && echo "Databricks auth OK" || echo "Databricks auth not configured (see docs/DATABRICKS.md)"
fi
echo "All checks finished."
