#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
: "${AIRADIO_APP_HOST:=0.0.0.0}"
: "${AIRADIO_APP_PORT:=18310}"
exec python3 -m uvicorn src.app_server:app --host "$AIRADIO_APP_HOST" --port "$AIRADIO_APP_PORT"
