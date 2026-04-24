# Must be run as Administrator (right-click -> Run as Administrator)
# Does two things: (1) port 80 -> 8080 forward, (2) allow inbound TCP 80 in firewall
# One-time setup, persists across reboots.

$ErrorActionPreference = "Stop"

if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "Run as Administrator"
    exit 1
}

Write-Host "Adding port proxy 80 -> 8080..." -ForegroundColor Cyan
netsh interface portproxy add v4tov4 listenport=80 listenaddress=0.0.0.0 connectport=8080 connectaddress=127.0.0.1

Write-Host "Adding firewall rule for port 80..." -ForegroundColor Cyan
netsh advfirewall firewall add rule name="SmartMat dev 80" dir=in action=allow protocol=TCP localport=80

Write-Host ""
Write-Host "Done. Current portproxy rules:" -ForegroundColor Green
netsh interface portproxy show v4tov4

Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. SSH to NAS, edit /volume1/docker/smartmat/.env:"
Write-Host "       DNS_TARGET_IP=192.168.68.227      (your Windows LAN IP)"
Write-Host "     then:  docker compose up -d dnsmasq"
Write-Host "  2. Back here:  .\scripts\dev.ps1"
Write-Host "  3. Wait ~5 min for devices to wake up."
