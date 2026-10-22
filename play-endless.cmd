@echo off
setlocal
chcp 65001 >nul
rem Full local stack with the endless test match: no zone shrink, no zone
rem damage, no timeout/death result. Default server lifetime is 7200 s.
call "%~dp0run-roe-2022.cmd" -Kit glider -Mode cycle -CycleScale 3 -ReliableUDP -IdleHandoff -WinterDoors -WinterWindows -DebugConsole -Target armored -Endless %*
exit /b %ERRORLEVEL%
