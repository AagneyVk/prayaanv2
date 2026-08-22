@echo off
setlocal
cd /d %~dp0

echo ========================================
echo   PRAYAAN V2 - Local Demo Launcher
echo ========================================

if not exist backend\.venv (
  echo [1/4] Creating backend virtual environment...
  py -m venv backend\.venv
)

echo [2/4] Installing backend dependencies...
call backend\.venv\Scripts\python.exe -m pip install -q -r backend\requirements.txt

if not exist frontend\node_modules (
  echo [3/4] Installing frontend dependencies...
  pushd frontend
  call npm install
  popd
) else (
  echo [3/4] Frontend dependencies already installed.
)

echo [4/4] Starting PRAYAAN V2...
start "PRAYAAN Backend" cmd /k "cd /d %~dp0backend && .venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"
start "PRAYAAN Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

timeout /t 4 /nobreak >nul
start http://localhost:5173

echo PRAYAAN V2 started.
endlocal
