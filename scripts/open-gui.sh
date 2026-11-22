#!/bin/sh
# Fixed entry point for the BinaryRepair GUI.
#
# Opens the stable address http://127.0.0.1:8124/welcome in the default browser
# after making sure both local GUIs are running:
#   - new conversation console .......... 127.0.0.1:8124
#   - reference v1.2.2 GUI ............. 127.0.0.1:8125 (switchable from /legacy)
#
# Usage:
#   ./scripts/open-gui.sh                 # check/start servers, open the page
#   BINARYREPAIR_NO_BROWSER=1 ./scripts/open-gui.sh   # servers only (CI/debug)
#
# Environment:
#   BINARYREPAIR_PYTHON      interpreter with fastapi+uvicorn (auto-detected)
#   BINARYREPAIR_OPEN_URL    page to open (default: http://127.0.0.1:8124/welcome)
#   BINARYREPAIR_NO_BROWSER  set to 1 to skip opening the browser
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
PORT=8124
LEGACY_PORT=8125
TOKEN_FILE="$ROOT/var/session.token"
URL="${BINARYREPAIR_OPEN_URL:-http://127.0.0.1:$PORT/welcome}"
LOG_DIR="${TMPDIR:-/tmp}"
NEW_LOG="$LOG_DIR/binaryrepair-gui-$PORT.log"
LEGACY_LOG="$LOG_DIR/binaryrepair-legacy-$LEGACY_PORT.log"

find_python() {
  if [ -n "${BINARYREPAIR_PYTHON:-}" ] && [ -x "$BINARYREPAIR_PYTHON" ]; then
    echo "$BINARYREPAIR_PYTHON"
    return 0
  fi
  for candidate in \
    "$ROOT/.venv/bin/python" \
    "$(cd "$ROOT/.." && pwd -P)/二进制2/.venv/bin/python" \
    "$HOME/Desktop/二进制2/.venv/bin/python" \
    "$(command -v python3 || true)"; do
    if [ -n "$candidate" ] && [ -x "$candidate" ] &&
       "$candidate" -c 'import fastapi, uvicorn' >/dev/null 2>&1; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

console_ok() {
  curl -fsS -m 2 "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1 &&
    curl -fsS -m 3 "http://127.0.0.1:$PORT/welcome" >/dev/null 2>&1
}

legacy_ok() {
  [ -s "$TOKEN_FILE" ] || return 1
  token="$(cat "$TOKEN_FILE")"
  code="$(curl -sS -m 2 -o /dev/null -w '%{http_code}' \
    "http://127.0.0.1:$LEGACY_PORT/?token=$token" 2>/dev/null || echo 000)"
  [ "$code" = "303" ] || [ "$code" = "200" ]
}

start_console() {
  if lsof -ti "tcp:$PORT" >/dev/null 2>&1; then
    pid="$(lsof -ti "tcp:$PORT" | head -1)"
    command="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    case "$command" in
      *"uvicorn app.main:app"*) lsof -ti "tcp:$PORT" | xargs kill 2>/dev/null || true ;;
      *) echo "[gui] port $PORT is used by another process; not touching it" >&2 ;;
    esac
    sleep 1
  fi
  python="$(find_python)" || {
    echo "[gui] no Python with fastapi+uvicorn found (set BINARYREPAIR_PYTHON)" >&2
    return 1
  }
  (
    cd "$ROOT"
    nohup "$python" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" \
      >>"$NEW_LOG" 2>&1 &
  )
  i=0
  while [ "$i" -lt 20 ]; do
    sleep 0.5
    console_ok && return 0
    i=$((i + 1))
  done
  echo "[gui] console did not become healthy; see $NEW_LOG" >&2
  return 1
}

start_legacy() {
  (
    cd "$ROOT"
    nohup ./scripts/start-legacy-gui.sh >>"$LEGACY_LOG" 2>&1 &
  )
  i=0
  while [ "$i" -lt 20 ]; do
    sleep 0.5
    legacy_ok && return 0
    i=$((i + 1))
  done
  echo "[legacy] reference GUI did not answer on port $LEGACY_PORT; see $LEGACY_LOG" >&2
  return 1
}

if ! console_ok; then
  start_console || exit 1
fi
if ! legacy_ok; then
  start_legacy || true
fi

echo ""
echo "  BinaryRepair · 固定入口"
echo "  新版 GUI : $URL"
echo "  档案库   : http://127.0.0.1:$PORT/ui/"
echo "  对话     : http://127.0.0.1:$PORT/ui/chat/"
echo "  旧版 GUI : http://127.0.0.1:$LEGACY_PORT/  （新版内点「旧版界面」自动带令牌）"
echo ""

if [ "${BINARYREPAIR_NO_BROWSER:-0}" != "1" ]; then
  if command -v open >/dev/null 2>&1; then
    open "$URL"
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL" >/dev/null 2>&1 || true
  fi
fi
