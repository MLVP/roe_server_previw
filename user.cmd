@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PY=%~dp0.tools\python\python.exe"
if not exist "%PY%" set "PY=python"
rem User manager: creates both ids (uid and actor uid) and the user folder.
rem   user.cmd add <name> [--nickname N] [--uid N] [--actor-uid HEX]
rem   user.cmd list | show <name> | remove <name>
"%PY%" -B -u "%~dp0tools\roe_user_manager.py" %*
exit /b %ERRORLEVEL%
