@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PY=%~dp0.tools\python\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" -B -u "%~dp0tools\roe_accounts.py" register %*
exit /b %ERRORLEVEL%
