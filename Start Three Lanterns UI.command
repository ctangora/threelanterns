#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

mkdir -p .run data

if [[ ! -d ".venv" ]]; then
  echo "[setup] creating virtual environment..."
  python3 -m venv .venv
fi

source ".venv/bin/activate"

if ! python -c "import fastapi, sqlalchemy, uvicorn" >/dev/null 2>&1; then
  echo "[setup] installing dependencies..."
  python -m pip install -e ".[dev]"
fi

export DATABASE_URL="${DATABASE_URL:-sqlite+pysqlite:///$ROOT_DIR/data/local_ui.db}"
export OPENAI_API_KEY="${OPENAI_API_KEY:-mock-local-key}"
export OPERATOR_ID="${OPERATOR_ID:-local_operator}"
export USE_MOCK_AI="${USE_MOCK_AI:-true}"

if [[ "${DRY_RUN:-0}" == "1" ]]; then
  echo "[dry-run] would bootstrap DB and start API + worker"
  exit 0
fi

python - <<'PY'
from app.models.base import Base
from app.database import engine
Base.metadata.create_all(bind=engine)
print("[setup] database schema ready")
PY

for service in api worker; do
  pid_file=".run/${service}.pid"
  if [[ -f "$pid_file" ]]; then
    old_pid="$(cat "$pid_file")"
    if kill -0 "$old_pid" >/dev/null 2>&1; then
      echo "[setup] stopping existing ${service} process ($old_pid)"
      kill "$old_pid" >/dev/null 2>&1 || true
      sleep 1
    fi
    rm -f "$pid_file"
  fi
done

nohup ".venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > ".run/api.log" 2>&1 &
echo $! > ".run/api.pid"

wait_for_api_health() {
  local attempts=25
  local delay=1
  for ((i=1; i<=attempts; i++)); do
    if curl -fsS "http://127.0.0.1:8000/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep "$delay"
  done
  return 1
}

if ! wait_for_api_health; then
  echo "[error] API failed health check at http://127.0.0.1:8000/health"
  echo "[error] See log: $ROOT_DIR/.run/api.log"
  if [[ -f ".run/api.pid" ]]; then
    api_pid="$(cat .run/api.pid)"
    if kill -0 "$api_pid" >/dev/null 2>&1; then
      kill "$api_pid" >/dev/null 2>&1 || true
    fi
    rm -f ".run/api.pid"
  fi
  exit 1
fi

nohup ".venv/bin/python" -m app.workers.run_worker > ".run/worker.log" 2>&1 &
echo $! > ".run/worker.pid"

open "http://127.0.0.1:8000/intake"

echo
echo "Three Lanterns UI is healthy and starting."
echo "UI: http://127.0.0.1:8000/intake"
echo "Health: http://127.0.0.1:8000/health"
echo "API log: $ROOT_DIR/.run/api.log"
echo "Worker log: $ROOT_DIR/.run/worker.log"
echo "Stop: double-click 'Stop Three Lanterns UI.command'"
