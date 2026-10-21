#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ ! -f backend/.env ]]; then
  echo "Missing backend/.env. Copy backend/.env.example and configure DATABASE_URL and HOST_LLM_API_KEY." >&2
  exit 1
fi
for path in backend/.venv/bin/python agents/.venv/bin/python frontend/node_modules; do
  if [[ ! -e "$path" ]]; then
    echo "Missing $path. See guide.md section 6 for dependency installation." >&2
    exit 1
  fi
done

set -a
source backend/.env
set +a
: "${DATABASE_URL:?Set DATABASE_URL in backend/.env to your local PostgreSQL database}"

if [[ -z "${AGENT_CHECKPOINT_DATABASE_URL:-}" ]]; then
  # The three Agent .env files can provide this individually.
  for name in k8s-orchestrator k8s-ops k8s-security; do
    if [[ ! -f "agents/$name/.env" ]] || ! grep -q '^AGENT_CHECKPOINT_DATABASE_URL=.' "agents/$name/.env"; then
      echo "Set AGENT_CHECKPOINT_DATABASE_URL in backend/.env or agents/$name/.env." >&2
      exit 1
    fi
  done
fi

for port in 8050 8051 8052 8053 5173; do
  if lsof -ti "TCP:$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port $port is already in use; stop that service before running this script." >&2
    exit 1
  fi
done

backend/.venv/bin/python -m backend.persistence.migrate

export PLAYGROUND_ALLOW_PRIVATE_AGENTS=true
export BOOTSTRAP_AGENTS="$(backend/.venv/bin/python - <<'PY'
import json
from pathlib import Path

import yaml

definitions = []
for path in sorted(Path('agents').glob('*/agent.yaml')):
    config = yaml.safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(config, dict):
        continue
    definitions.append({
        'id': config['agent_id'],
        'url': f"http://127.0.0.1:{config['port']}",
    })
print(json.dumps(definitions))
PY
)"

pids=()
cleanup() {
  trap - INT TERM EXIT
  for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
  wait "${pids[@]}" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

mkdir -p logs
start() {
  local name="$1"
  shift
  "$@" >"logs/$name.log" 2>&1 &
  pids+=("$!")
  echo "Started $name (PID $!, logs/$name.log)"
}

start orchestrator agents/.venv/bin/python agents/k8s-orchestrator/main.py
start ops agents/.venv/bin/python agents/k8s-ops/main.py
start security agents/.venv/bin/python agents/k8s-security/main.py

for port in 8051 8052 8053; do
  ready=false
  for attempt in {1..30}; do
    if curl --silent --fail "http://127.0.0.1:$port/.well-known/agent-card.json" >/dev/null; then
      ready=true
      break
    fi
    sleep 1
  done
  if [[ "$ready" != true ]]; then
    echo "Agent on port $port did not become ready; check logs/*.log." >&2
    exit 1
  fi
done

start backend backend/.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8050
start frontend npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173 --strictPort

echo "Open http://127.0.0.1:5173 (Ctrl+C to stop)."
while :; do
  for pid in "${pids[@]}"; do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "A service exited. Check logs/*.log." >&2
      exit 1
    fi
  done
  sleep 1
done
