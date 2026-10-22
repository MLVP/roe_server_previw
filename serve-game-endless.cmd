@echo off
setlocal
chcp 65001 >nul
if "%~1"=="" (
  echo Usage: serve-game-endless.cmd ^<name^> [extra options]
  echo    Starts only the local server stack in endless mode ^(no zone shrink,
  echo    no damage, no match timeout^). Then run play-client.cmd in a second window.
  echo    Extra options: -Duration N ^(default 7200^), -SelectionSeconds N ^(default 7^), -LootCatalog FILE
  exit /b 2
)
call "%~dp0serve-game.cmd" "%~1" -Endless %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%
