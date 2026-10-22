@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PY=%~dp0.tools\python\python.exe"
if not exist "%PY%" set "PY=python"
rem First working test: login server starts the room, client enters the game.
rem Use --launch-client to start the real client and wait for the room entry.
"%PY%" -X utf8 -B -u "%~dp0tools\login_room_check_2022.py" %*
exit /b %ERRORLEVEL%
