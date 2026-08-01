@echo off
setlocal
cd /d "%~dp0"

set "QIDIAN_GATEWAY_PORT=8000"
if exist ".env" (
  for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    if /I "%%A"=="PORT" set "QIDIAN_GATEWAY_PORT=%%B"
  )
)

echo Starting Qidian Agent development environment...
echo Starting Docker backend on port %QIDIAN_GATEWAY_PORT%...
docker compose -f docker-compose.dev.yml stop frontend >nul 2>&1
docker compose -f docker-compose.dev.yml up -d --wait gateway
if errorlevel 1 (
  echo Failed to start the Docker backend.
  exit /b 1
)

if not exist "frontend\node_modules" (
  echo Installing frontend dependencies...
  pushd frontend
  call npm ci
  if errorlevel 1 (
    popd
    echo Failed to install frontend dependencies.
    exit /b 1
  )
  popd
)

echo Starting host Vite frontend...
pushd frontend
start "Qidian Agent Frontend" cmd /k "set VITE_PROXY_TARGET=http://127.0.0.1:%QIDIAN_GATEWAY_PORT%&& npm run dev -- --host 0.0.0.0"
popd

echo Frontend: http://localhost:5173
echo Gateway:  http://localhost:%QIDIAN_GATEWAY_PORT%
echo Development environment started.
endlocal

