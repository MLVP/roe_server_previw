param(
    [ValidateSet('off', 'on', 'status')]
    [string]$Mode = 'status',
    [string]$Client = ''
)
# Telemetry switch: Tencent Bugly/TQM crash collector.
#
# The client loads GbSpy64.dll, which starts TQM64\TQMCenter_64.exe - a crash
# and telemetry collector (bugly-tqm-client). It reserves about a gigabyte of
# private memory for dumps; the game works normally without it.
#
# The switch is a file permission on that one executable: no extra process and
# no change to the game files. "off" denies the execute right to the current
# user, "on" removes the deny, "status" only reports.
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
if (-not $Client) {
    $saved = Join-Path $repo '.tools\client-path.txt'
    if (Test-Path -LiteralPath $saved -PathType Leaf) { $Client = ([IO.File]::ReadAllText($saved)).Trim() }
}
if (-not $Client) { $Client = Read-Host 'Game folder / Папка игры' }
$Client = [IO.Path]::GetFullPath($Client.Trim().Trim('"').Trim("'"))
$target = Join-Path $Client 'TQM64\TQMCenter_64.exe'
if (-not (Test-Path -LiteralPath $target -PathType Leaf)) {
    Write-Host ('Нет файла телеметрии: ' + $target) -ForegroundColor Yellow
    exit 0
}
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
switch ($Mode) {
    'off' {
        & icacls.exe $target /deny "${user}:(X)" | Out-Null
        Write-Host ('Телеметрия отключена: запрет запуска ' + $target)
        Write-Host 'Вернуть: telemetry.cmd on'
    }
    'on' {
        & icacls.exe $target /remove:d $user | Out-Null
        Write-Host ('Телеметрия разрешена: ' + $target)
    }
    'status' {
        $lines = & icacls.exe $target
        $deny = $lines | Where-Object { $_ -match '\(DENY\)' }
        if ($deny) { Write-Host ('Телеметрия отключена: ' + $deny) }
        else { Write-Host 'Телеметрия разрешена (файл можно запускать).' }
    }
}
exit 0
