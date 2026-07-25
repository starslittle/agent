@echo off
setlocal

set args=%*
echo %args% | findstr /I "--port" >nul
if %errorlevel%==0 goto run

rem If no explicit port, default to 8000
set args=%args% --port 8000

:run
python -m uvicorn %args%
