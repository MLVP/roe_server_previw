@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"

if "%~1"=="" (
  set "MODE=dion"
) else (
  set "MODE=%~1"
  shift
)

set "EXTRA="
:collect
if "%~1"=="" goto run
set "EXTRA=!EXTRA! "%~1""
shift
goto collect

:run
set "PY=%~dp0.tools\python\python.exe"
if not exist "%PY%" set "PY=python"
echo Room mode: %MODE%
echo API: http://127.0.0.1:18080/api/status
"%PY%" -X utf8 -B -u "%~dp0server\room_manager.py" --mode "%MODE%" %EXTRA%
exit /b %ERRORLEVEL%
