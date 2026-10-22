# Launch only the Ring of Elysium client, without starting the local server.
# Use together with serve-game.cmd (server-only). The server applies the
# account identity (UID/nickname), so the client itself stays generic.
# The login id (-uid=) comes from users/registry.json when -Profile is given.
param(
    [string]$Client = '',
    [string]$Server = '127.0.0.1:8001',
    [string]$Language = 'en',
    [string]$Profile = '',
    [int]$Uid = 0,
    [switch]$Wait
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'select_client.ps1')
$folder = Select-RoeClient -Client $Client -Repository $repo
$exe = Join-Path $folder 'Europa_Client.exe'
# Сборщик крашей Tencent клиенту не нужен и резервирует около гигабайта памяти.
# Отключаем запретом запуска: ни лишнего процесса, ни правки файлов игры.
& (Join-Path $PSScriptRoot 'telemetry_switch.ps1') -Mode off -Client $folder | Out-Null
if ($Uid -eq 0) {
    $Uid = 1
    if ($Profile) {
        $registryPath = Join-Path $repo 'users\registry.json'
        if (Test-Path -LiteralPath $registryPath -PathType Leaf) {
            $registry = Get-Content -LiteralPath $registryPath -Raw -Encoding UTF8 | ConvertFrom-Json
            foreach ($row in $registry.PSObject.Properties) {
                if ($row.Value.name -eq $Profile) { $Uid = [int]$row.Value.uid; break }
            }
        }
    }
}
$arguments = @("-language=$Language", '-garena', "-uid=$Uid", "-server=$Server")
Write-Host ("Client: {0} -> {1} (uid {2})" -f $folder, $Server, $Uid)
if ($Wait) {
    $process = Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory $folder -PassThru -Wait
    exit $process.ExitCode
} else {
    $process = Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory $folder -PassThru
    Write-Host ("Client PID: {0}" -f $process.Id)
}
