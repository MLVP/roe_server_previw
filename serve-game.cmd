@echo off
setlocal
chcp 65001 >nul
if "%~1"=="" (
  echo Usage: serve-game.cmd ^<name^> [extra options]
  echo    Starts only the local server stack ^(lobby 9001, proxy 8001, UDP endpoint^).
  echo    Then run play-client.cmd in a second window to attach a game client.
  echo    Extra options: -Endless, -SelectionSeconds N, -Duration N, -LootCatalog FILE, -NoLootCatalog
  exit /b 2
)
call "%~dp0run-roe-2022.cmd" -Kit glider -Mode cycle -CycleScale 3 -ReliableUDP -IdleHandoff -WinterDoors -WinterWindows -Target armored -Profile "%~1" -ServicesOnly %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%
