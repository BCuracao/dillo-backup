#!/usr/bin/env bash
# ─────────────────────────────────────────────────────
#  Dillo — Development Launcher (Unix)
#  Starts both the FastAPI backend and Next.js frontend.
# ─────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "  ========================================"
echo "   Dillo — Dev Launcher"
echo "  ========================================"
echo ""

# Start FastAPI backend
echo "[*] Starting FastAPI backend on http://localhost:8000 ..."
cd "$SCRIPT_DIR/backend"
source venv/bin/activate
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 --app-dir .. &
BACKEND_PID=$!

sleep 2

# Start Next.js frontend
echo "[*] Starting Next.js frontend on http://localhost:3000 ..."
cd "$SCRIPT_DIR/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "[OK] Both servers are starting."
echo "     Backend:  http://localhost:8000/docs"
echo "     Frontend: http://localhost:3000"
echo ""
echo "Press Ctrl+C to stop both servers."

# Trap Ctrl+C to kill both processes
trap "echo ''; echo 'Shutting down...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM

wait
