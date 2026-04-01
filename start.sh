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
pip install -q -r requirements.txt 2>/dev/null

# Install Node.js dependencies for dashboard
echo "[2/4] Installing dashboard dependencies..."
cd dashboard && npm install --silent 2>/dev/null && cd ..

# Start FastAPI backend on port 8000
echo "[3/4] Starting FastAPI API server on :8000..."
python api_server.py &
API_PID=$!

# Wait for API to be ready
sleep 2

# Start Next.js dashboard on port 3000
echo "[4/4] Starting Next.js dashboard on :3000..."
cd dashboard && npx next dev -p 3000 &
DASH_PID=$!

echo ""
echo "========================================="
echo "  ✓ API Server:  http://localhost:8000"
echo "  ✓ Dashboard:   http://localhost:3000"
echo "  ✓ API Docs:    http://localhost:8000/docs"
echo "========================================="
echo ""
echo "Press Ctrl+C to stop all services"

# Wait for both processes
wait $API_PID $DASH_PID
