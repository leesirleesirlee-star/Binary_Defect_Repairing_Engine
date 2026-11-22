#!/bin/sh
# Open the reference v1.2.2 GUI beside the new conversation console.
#
# Both applications share this console's local session token (browsers key the
# ``br_session`` cookie by host, not by port), so switching in either direction
# keeps the local session. The console serves /legacy as the forward link; this
# script only starts the reference application.
#
# Usage:
#   ./scripts/start-legacy-gui.sh
#   BINARYREPAIR_LEGACY_PORT=8125 ./scripts/start-legacy-gui.sh
#
# Environment:
#   BINARYREPAIR_LEGACY_DIR   reference GUI checkout (default: ../binary-repair-gui)
#   BINARYREPAIR_LEGACY_PORT  port for the reference GUI (default: 8125)
set -eu

NEW_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LEGACY_DIR="${BINARYREPAIR_LEGACY_DIR:-$(cd "$NEW_ROOT/.." && pwd -P)/binary-repair-gui}"
PORT="${BINARYREPAIR_LEGACY_PORT:-8125}"
TOKEN_FILE="${BINARYREPAIR_SESSION_TOKEN_FILE:-$NEW_ROOT/var/session.token}"

if [ ! -x "$LEGACY_DIR/.venv/bin/python" ]; then
  echo "[legacy] missing $LEGACY_DIR/.venv/bin/python" >&2
  echo "[legacy] run the reference start-gui.sh once to create its venv" >&2
  exit 1
fi
if [ ! -s "$TOKEN_FILE" ]; then
  echo "[legacy] missing session token $TOKEN_FILE" >&2
  exit 1
fi

TOKEN="$(cat "$TOKEN_FILE")"
export BINARYREPAIR_SESSION_TOKEN="$TOKEN"
export BINARYREPAIR_PORT="$PORT"
cd "$LEGACY_DIR"

echo "[legacy] reference GUI: http://127.0.0.1:${PORT}/"
echo "[legacy] open it from the new console: http://127.0.0.1:8124/legacy"
exec "$LEGACY_DIR/.venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
