@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PY=%~dp0.tools\python\python.exe"
if not exist "%PY%" set "PY=python"
rem Starts the three local services: accounts (8099), lobby (8001 + API 8010)
rem and the room manager (18080). Configs: config\accounts.json,
rem config\lobby.json, config\room.json. Ctrl+C stops everything.
"%PY%" -X utf8 -B -u "%~dp0tools\serve_all_2022.py" %*
exit /b %ERRORLEVEL%
