@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PY=%~dp0.tools\python\python.exe"
if not exist "%PY%" set "PY=python"
rem Accounts service only (HTTP 8099): users, registration, profiles.
rem For the whole stack use serve-all.cmd (accounts + lobby + room manager).
"%PY%" -X utf8 -B -u "%~dp0tools\roe_accounts.py" serve %*
exit /b %ERRORLEVEL%
