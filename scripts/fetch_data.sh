#!/usr/bin/env bash
# Downloads the official Dashboard Royale dataset (~1 GB with extracted files) into data/raw.
set -euo pipefail
cd "$(dirname "$0")/.."
DEST=data/raw/dashboard-royale
if [[ -d "$DEST/.git" ]]; then
  git -C "$DEST" pull --ff-only
else
  git clone --depth 1 https://github.com/tamu-datathon-org/dashboard-royale.git "$DEST"
fi
echo "Data at $DEST/data"
