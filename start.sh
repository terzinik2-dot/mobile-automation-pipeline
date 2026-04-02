#!/bin/bash
# =============================================================================
# Mobile Automation Pipeline — Replit Start Script
# Запускает FastAPI backend + Next.js dashboard одной командой
# =============================================================================

set -e

echo "========================================="
echo "  Mobile Automation Pipeline"
echo "  Starting services..."
echo "========================================="

# Install Python dependencies
echo "[1/4] Installing Python dependencies..."
pip install -q -r requirements.txt 2>&1 | tail -5

# Install Node.js dependencies for dashboard
echo "[2/4] Installing dashboard dependencies..."
cd dashboard && npm install --silent 2>&1 | tail -3 && cd ..

# Build Next.js for production
echo "[3/4] Building Next.js dashboard..."
cd dashboard && npx next build 2>&1 | tail -10 && cd ..

# Start FastAPI backend on port 8000
echo "[4/4] Starting servers..."
python api_server.py &
API_PID=$!

# Wait for API to be ready
sleep 3

# Start Next.js dashboard on port 3000
cd dashboard && npx next start -p 3000 &
DASH_PID=$!

echo ""
echo "========================================="
echo "  API Server:  http://0.0.0.0:8000"
echo "  Dashboard:   http://0.0.0.0:3000"
echo "  API Docs:    http://0.0.0.0:8000/docs"
echo "========================================="
echo ""

# Trap to clean up on exit
trap "kill $API_PID $DASH_PID 2>/dev/null; exit 0" SIGINT SIGTERM

# Wait for both processes
wait $API_PID $DASH_PID
