@echo off
echo Starting Qidian AI Agent...

:: 1. 启动后端 (在新的窗口中)
echo Starting Backend...
start "Qidian Agent Backend" cmd /k "call conda activate my_agent && uvicorn src.api.main:app --host 0.0.0.0 --port 8002 --reload"

:: 2. 启动前端 (在新的窗口中)
echo Starting Frontend...
cd frontend
start "Qidian Agent Frontend" cmd /k "pnpm run dev"

echo Done! Windows have been opened.

