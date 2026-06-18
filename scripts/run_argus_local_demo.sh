#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT_DIR"

port_in_use() {
  local port="$1"
  ss -ltn | awk '{print $4}' | grep -Eq "[:.]${port}$"
}

ENV_FILE="${ARGUS_ENV_FILE:-$ROOT_DIR/.env}"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$ENV_FILE"
  set +a
fi

PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  if [ -x "$ROOT_DIR/.venv/bin/python" ]; then
    PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
  else
    PYTHON_BIN="python"
  fi
fi

RUNTIME_TMPDIR="${ARGUS_TMPDIR:-/tmp}"
export TMPDIR="$RUNTIME_TMPDIR"
export TMP="$RUNTIME_TMPDIR"
export TEMP="$RUNTIME_TMPDIR"

build_postgres_url() {
  if [ -n "${POSTGRES_URL:-}" ]; then
    printf "%s\n" "$POSTGRES_URL"
    return
  fi
  if [ -z "${DB_USER:-}" ] || [ -z "${DB_PASSWORD:-}" ] || [ -z "${DB_HOST:-}" ] || [ -z "${DB_NAME:-}" ]; then
    return
  fi
  "$PYTHON_BIN" - <<'PY'
import os
from urllib.parse import quote

user = quote(os.environ["DB_USER"], safe="")
password = quote(os.environ["DB_PASSWORD"], safe="")
host = os.environ.get("DB_HOST") or "127.0.0.1"
port = os.environ.get("DB_PORT") or "5432"
name = quote(os.environ["DB_NAME"], safe="")
print(f"postgresql://{user}:{password}@{host}:{port}/{name}")
PY
}

BACKEND_HOST="127.0.0.1"
BACKEND_PORT="5000"
export POSTGRES_URL="${POSTGRES_URL:-$(build_postgres_url)}"
export BETTAFISH_BACKEND_URL="${BETTAFISH_BACKEND_URL:-http://${BACKEND_HOST}:${BACKEND_PORT}}"
export NEXT_PUBLIC_BETTAFISH_BACKEND_URL="${NEXT_PUBLIC_BETTAFISH_BACKEND_URL:-$BETTAFISH_BACKEND_URL}"
export AUTH_SECRET="${AUTH_SECRET:-local-argus-demo-secret}"

FRONTEND_PORT="${ARGUS_FRONTEND_PORT:-3010}"
if [ "$FRONTEND_PORT" = "3010" ] && port_in_use "3010"; then
  FRONTEND_PORT="3100"
  echo "Port 3010 is in use; using frontend port 3100."
fi
if port_in_use "$FRONTEND_PORT"; then
  echo "Frontend port $FRONTEND_PORT is already in use." >&2
  exit 1
fi

"$PYTHON_BIN" scripts/argus_demo_preflight.py

(
  cd apps/argus-saas
  pnpm exec tsx lib/db/migrate.ts
)

backend_pid=""
frontend_pid=""

cleanup() {
  if [ -n "$frontend_pid" ]; then
    kill "$frontend_pid" 2>/dev/null || true
  fi
  if [ -n "$backend_pid" ]; then
    kill "$backend_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

HOST="$BACKEND_HOST" PORT="$BACKEND_PORT" "$PYTHON_BIN" app.py &
backend_pid=$!

(
  cd apps/argus-saas
  PORT="$FRONTEND_PORT" \
    AUTH_SECRET="$AUTH_SECRET" \
    BETTAFISH_BACKEND_URL="$BETTAFISH_BACKEND_URL" \
    NEXT_PUBLIC_BETTAFISH_BACKEND_URL="$NEXT_PUBLIC_BETTAFISH_BACKEND_URL" \
    pnpm dev
) &
frontend_pid=$!

echo "Backend:  $BETTAFISH_BACKEND_URL"
echo "Frontend: http://localhost:${FRONTEND_PORT}"
echo "Press Ctrl-C to stop both services."

wait -n "$backend_pid" "$frontend_pid"
