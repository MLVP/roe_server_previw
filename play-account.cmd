@echo off
setlocal
chcp 65001 >nul
if "%~1"=="" goto usage
rem If a local server is already up (serve-login.cmd / serve-room.cmd),
rem start only the client: the player identity comes from that server.
set "ROE_SERVER_UP="
for /f "usebackq delims=" %%i in (`powershell.exe -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue) { 'up' }"`) do set "ROE_SERVER_UP=%%i"
if "%ROE_SERVER_UP%"=="up" goto client_only
call "%~dp0play.cmd" -Profile "%~1" %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:client_only
echo Local server is already running on 127.0.0.1:8001 - starting the client only.
echo The player identity comes from the server: the login id is taken from
echo users\registry.json by the profile name.
call "%~dp0play-client.cmd" -Profile "%~1"
exit /b %ERRORLEVEL%

:usage
echo Usage: play-account.cmd ^<name^>
echo    or: play.cmd -Profile ^<name^> [extra options]
exit /b 2
