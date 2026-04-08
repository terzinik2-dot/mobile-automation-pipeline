#!/bin/bash
# Mobile Automation Pipeline — Replit Start Script

WORKSPACE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== Mobile Automation Pipeline ==="
echo "Working dir: $WORKSPACE_DIR"

# Install Python deps
echo "[1/3] Installing Python dependencies..."
pip install -q fastapi uvicorn sqlalchemy aiosqlite loguru pydantic pydantic-settings websockets 2>&1 | tail -3

# Start FastAPI on port 8000
echo "[2/3] Starting FastAPI on :8000..."
cd "$WORKSPACE_DIR"
python api_server.py &
API_PID=$!
sleep 3
echo "API PID: $API_PID"

# Install Node deps and start Next.js dev on port 3000
echo "[3/3] Starting Next.js dashboard on :3000..."
cd "$WORKSPACE_DIR/dashboard"
npm install --silent 2>/dev/null
npx next dev -p 3000 &
DASH_PID=$!

echo ""
echo "==================================="
echo "API:       http://0.0.0.0:8000"
echo "Dashboard: http://0.0.0.0:3000"
echo "API Docs:  http://0.0.0.0:8000/docs"
echo "==================================="

trap "kill $API_PID $DASH_PID 2>/dev/null; exit 0" SIGINT SIGTERM
wait $API_PID $DASH_PID
