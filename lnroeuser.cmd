@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PY=%~dp0.tools\python\python.exe"
if not exist "%PY%" set "PY=python"
rem Creates a Windows shortcut for a local client:
rem   lnroeuser.cmd -uid [uid] -f [game folder] -o [shortcut path]
rem Optional: -s [host:port] of the lobby service (default 127.0.0.1:8001).
"%PY%" -B -u "%~dp0tools\lnroeuser.py" %*
exit /b %ERRORLEVEL%
