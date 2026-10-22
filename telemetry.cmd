@echo off
setlocal
chcp 65001 >nul
rem Telemetry switch for the Tencent Bugly/TQM crash collector.
rem   telemetry.cmd off   - forbid launching TQM64\TQMCenter_64.exe
rem   telemetry.cmd on    - allow it again
rem   telemetry.cmd status - report the current state
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\telemetry_switch.ps1" -Mode %1 -Client "%~2"
exit /b %ERRORLEVEL%
