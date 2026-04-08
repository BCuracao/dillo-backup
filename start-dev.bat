@echo off
REM ─────────────────────────────────────────────────────
REM  Dillo — Development Launcher (Windows)
REM  Starts both the FastAPI backend and Next.js frontend.
REM ─────────────────────────────────────────────────────

echo.
echo  ========================================
echo   Dillo - Dev Launcher
echo  ========================================
echo.

REM Start the FastAPI backend (port 8000)
echo [*] Starting FastAPI backend on http://localhost:8000 ...
start "Dillo-Backend" cmd /k "cd /d %~dp0backend && venv\Scripts\python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 --app-dir .."

REM Give the backend a moment to start
timeout /t 3 /nobreak > nul

REM Start the Next.js frontend (port 3000)
echo [*] Starting Next.js frontend on http://localhost:3000 ...
start "Dillo-Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo [OK] Both servers are starting.
echo      Backend:  http://localhost:8000/docs
echo      Frontend: http://localhost:3000
echo.
pause
