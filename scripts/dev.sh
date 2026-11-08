#!/usr/bin/env bash
# Starts backend and frontend together; Ctrl+C stops both.
set -euo pipefail
cd "$(dirname "$0")"
./dev-backend.sh & BACK=$!
./dev-frontend.sh & FRONT=$!
trap 'kill $BACK $FRONT 2>/dev/null' EXIT INT TERM
wait
