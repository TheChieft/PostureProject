#!/usr/bin/env bash
# sync_and_run.sh
# Syncs the project to a Windows-native directory, then launches the app.
#
# Usage (from WSL):
#   ./sync_and_run.sh              # sync + run
#   ./sync_and_run.sh --preview    # sync + run with camera preview window
#   ./sync_and_run.sh --no-run     # sync only (skip launching the app)

set -e

# ── Config ────────────────────────────────────────────────────────────────────
WINDOWS_USER="andre"
WIN_DEST="/mnt/c/Users/$WINDOWS_USER/PostureProject"
SRC="$(cd "$(dirname "$0")" && pwd)"

# Extra args forwarded to main.py (e.g. --preview, --camera 1)
EXTRA_ARGS=()
NO_RUN=false

for arg in "$@"; do
    if [[ "$arg" == "--no-run" ]]; then
        NO_RUN=true
    else
        EXTRA_ARGS+=("$arg")
    fi
done

# ── Sync ──────────────────────────────────────────────────────────────────────
echo "→ Syncing $SRC → $WIN_DEST"
mkdir -p "$WIN_DEST"
mkdir -p "$WIN_DEST/assets"
mkdir -p "$WIN_DEST/logs"

rsync -a --delete \
    --exclude='.git/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.conda/' \
    --exclude='.venv/' \
    --exclude='dist/' \
    --exclude='build/' \
    --exclude='logs/' \
    --exclude='*.spec' \
    --exclude='build.ps1' \
    --exclude='sync_and_run.sh' \
    --exclude='version_info.txt' \
    "$SRC/" "$WIN_DEST/"

echo "✓ Sync complete"

if $NO_RUN; then
    echo "→ --no-run specified, skipping launch."
    exit 0
fi

# ── Launch ────────────────────────────────────────────────────────────────────
WIN_PATH="C:\\Users\\$WINDOWS_USER\\PostureProject"
ARGS_STR="${EXTRA_ARGS[*]}"

echo "→ Launching app from $WIN_PATH ..."
powershell.exe -NoProfile -Command "
    Set-Location '$WIN_PATH'
    py -3.11 main.py $ARGS_STR
"
