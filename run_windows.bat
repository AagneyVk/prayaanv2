@echo off
setlocal
cd /d %~dp0

echo ========================================
echo   PRAYAAN V2 - Local Demo Launcher
echo ========================================

if not exist backend\.venv (
  echo [1/5] Creating backend virtual environment...
  py -m venv backend\.venv
) else (
  echo [1/5] Backend environment ready.
)

echo [2/5] Syncing backend dependencies...
echo       First SUMO install can be large; later runs reuse the environment.
call backend\.venv\Scripts\python.exe -m pip install -q -r backend\requirements.txt
if errorlevel 1 (
  echo Backend dependency installation failed.
  pause
  exit /b 1
)

echo [3/5] Syncing frontend dependencies...
pushd frontend
call npm install --silent
if errorlevel 1 (
  popd
  echo Frontend dependency installation failed.
  pause
  exit /b 1
)
popd

echo [4/5] Starting FastAPI backend...
start "PRAYAAN Backend" cmd /k "cd /d %~dp0backend && .venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"

echo [5/5] Starting Vite command center...
start "PRAYAAN Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

timeout /t 5 /nobreak >nul
start http://localhost:5173

echo.
echo PRAYAAN V2 started.
echo Open any bus ^> OPEN MICRO TWIN for SUMO physics.
endlocal
