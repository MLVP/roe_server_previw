@echo off
setlocal
rem Stops the local stack of this repository: the accounts service, the lobby
rem (8001 + API 8010), the room manager (18080), the game endpoint and client.
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ports = 8001,8010,8099,9001,18001,18080,19001; $pids = @(); $pids += Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $ports -contains $_.LocalPort } | Select-Object -ExpandProperty OwningProcess; $pids += Get-NetUDPEndpoint -ErrorAction SilentlyContinue | Where-Object { $ports -contains $_.LocalPort } | Select-Object -ExpandProperty OwningProcess; foreach ($id in ($pids | Sort-Object -Unique)) { if ($id -and $id -gt 0) { Write-Host ('stop pid ' + $id); & taskkill /PID $id /T /F 2>&1 | Out-Null } }"
taskkill /IM Europa_Client.exe /T /F >nul 2>&1
echo Local stack stopped.
exit /b 0
