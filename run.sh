#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_PORT=8050
FRONTEND_PORT=5174

# Kill old processes on our fixed ports
kill_port() {
  local pid
  pid=$(lsof -ti ":$1" 2>/dev/null || true)
  if [ -n "$pid" ]; then
    echo "Killing old process on port $1 (PID $pid)"
    kill $pid 2>/dev/null || true
    sleep 1
  fi
}

kill_port $BACKEND_PORT
kill_port $FRONTEND_PORT

# ── Backend ──
echo "==> Starting backend on port $BACKEND_PORT..."
cd "$ROOT/backend"

# Create venv if needed
if [ ! -d .venv ]; then
  echo "  Creating .venv..."
  python3 -m venv .venv
fi

# Install core dependencies
echo "  Installing dependencies..."
.venv/bin/pip install -q fastapi uvicorn httpx pydantic python-dotenv 2>&1 | tail -1

# Install a2a-sdk
echo "  Installing a2a-sdk..."
.venv/bin/pip install -q "a2a-sdk>=0.3.25" 2>&1 | tail -1 || echo "  WARNING: a2a-sdk install issue"

# Install LangGraph dependencies
echo "  Installing langgraph dependencies..."
.venv/bin/pip install -q langgraph langchain-openai langchain-core 2>&1 | tail -1 || echo "  WARNING: langgraph install issue"

# Install google-adk
echo "  Installing google-adk..."
.venv/bin/pip install -q google-adk 2>&1 | tail -1 || echo "  WARNING: google-adk install issue"

echo "  Starting server..."
.venv/bin/python3 -m uvicorn main:app --host 127.0.0.1 --port $BACKEND_PORT --log-level info &
BACKEND_PID=$!
sleep 2

# ── Frontend ──
echo "==> Starting frontend on port $FRONTEND_PORT..."
cd "$ROOT/frontend"
if [ ! -d node_modules ]; then
  echo "  Installing npm packages..."
  npm install
fi
npx vite --host 127.0.0.1 --port $FRONTEND_PORT &
FRONTEND_PID=$!

echo ""
echo "  Backend:  http://127.0.0.1:$BACKEND_PORT"
echo "  Frontend: http://127.0.0.1:$FRONTEND_PORT"
echo ""
echo "Press Ctrl+C to stop both."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM
wait
