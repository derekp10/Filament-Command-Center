#!/usr/bin/env bash
# reset-dev (POSIX host wrapper) — restore the shared dev backend to a clean
# seed baseline before an E2E sweep. Group 19.1.
#
# Thin wrapper around reset_dev.py for Linux/macOS hosts (e.g. running the
# reset from the TrueNAS box). Runs on the HOST: it docker-restarts the
# inventory_hub container and rewrites the bind-mounted locations.json, and
# reaches dev Spoolman at DEV_SPOOLMAN_URL (default http://192.168.1.29:7913).
#
# Usage:
#   ./reset-dev.sh                  # non-destructive restore + docker restart
#   ./reset-dev.sh --dry-run --prune
#   ./reset-dev.sh --prune          # restore AND delete sweep-created records
#   ./reset-dev.sh --capture        # re-snapshot current dev into seeds/
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PYTHON:-python3}"
exec "$PY" "$HERE/reset_dev.py" "$@"
