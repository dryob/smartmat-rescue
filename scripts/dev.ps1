# Windows dev server (port 8080).
# For real devices: run setup-dev-port80.ps1 once (as Admin) to forward 80 -> 8080,
# and on NAS set DNS_TARGET_IP=<your Windows IP> in /volume1/docker/smartmat/.env

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$env:SMARTMAT_DB = Join-Path $root "data\smartmat.db"
$env:LOG_LEVEL = "INFO"
$env:PORT = "8080"

New-Item -ItemType Directory -Force -Path (Split-Path $env:SMARTMAT_DB) | Out-Null

$route = Get-NetRoute -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue | Sort-Object -Property RouteMetric | Select-Object -First 1
if ($route) {
    $winIp = (Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $route.InterfaceIndex -ErrorAction SilentlyContinue | Select-Object -First 1).IPAddress
}

Write-Host ""
Write-Host "SmartMat dev server" -ForegroundColor Cyan
Write-Host "  listen    : http://0.0.0.0:8080"
Write-Host "  dashboard : http://127.0.0.1:8080/"
if ($winIp) {
    Write-Host "  LAN IP    : $winIp   (devices hit port 80 -> forwarded to 8080)"
}
Write-Host "  db        : $($env:SMARTMAT_DB)"
Write-Host ""
Write-Host "Ctrl+C to stop. Restart manually after code changes (no auto-reload)." -ForegroundColor Yellow
Write-Host ""

& "$root\.venv\Scripts\python.exe" "$root\app\main.py"
