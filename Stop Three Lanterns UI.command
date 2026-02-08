#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

stop_service() {
  local service="$1"
  local pid_file=".run/${service}.pid"

  if [[ ! -f "$pid_file" ]]; then
    echo "[stop] ${service}: no pid file"
    return
  fi

  local pid
  pid="$(cat "$pid_file")"
  if kill -0 "$pid" >/dev/null 2>&1; then
    kill "$pid" >/dev/null 2>&1 || true
    echo "[stop] ${service}: stopped pid $pid"
  else
    echo "[stop] ${service}: process not running (pid $pid)"
  fi
  rm -f "$pid_file"
}

stop_service "api"
stop_service "worker"

echo "Three Lanterns processes stopped."

