# Must be run as Administrator
# Removes portproxy + firewall rule created by setup-dev-port80.ps1

$ErrorActionPreference = "Continue"

if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "Run as Administrator"
    exit 1
}

Write-Host "Removing port proxy..." -ForegroundColor Cyan
netsh interface portproxy delete v4tov4 listenport=80 listenaddress=0.0.0.0

Write-Host "Removing firewall rule..." -ForegroundColor Cyan
netsh advfirewall firewall delete rule name="SmartMat dev 80"

Write-Host ""
Write-Host "Remaining portproxy rules:" -ForegroundColor Green
netsh interface portproxy show v4tov4

Write-Host ""
Write-Host "Don't forget to revert NAS dnsmasq:" -ForegroundColor Yellow
Write-Host "  Remove DNS_TARGET_IP from /volume1/docker/smartmat/.env"
Write-Host "  docker compose up -d dnsmasq"
