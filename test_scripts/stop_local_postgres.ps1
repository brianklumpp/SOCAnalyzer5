# Stop and disable local PostgreSQL service
# Run this script as Administrator

Write-Host "🛑 Stopping Local PostgreSQL Service" -ForegroundColor Cyan
Write-Host ""

# Check if running as Administrator
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
$isAdmin = $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "❌ This script must be run as Administrator!" -ForegroundColor Red
    Write-Host "Right-click PowerShell and select 'Run as Administrator', then run this script again." -ForegroundColor Yellow
    exit 1
}

# Stop PostgreSQL service
Write-Host "Stopping postgresql-x64-17 service..." -ForegroundColor Yellow
try {
    Stop-Service -Name "postgresql-x64-17" -Force -ErrorAction Stop
    Write-Host "✅ Service stopped" -ForegroundColor Green
} catch {
    Write-Host "⚠️  Could not stop service: $_" -ForegroundColor Yellow
}

# Disable PostgreSQL service (so it doesn't start on boot)
Write-Host "`nDisabling postgresql-x64-17 service..." -ForegroundColor Yellow
try {
    Set-Service -Name "postgresql-x64-17" -StartupType Disabled -ErrorAction Stop
    Write-Host "✅ Service disabled (will not start on boot)" -ForegroundColor Green
} catch {
    Write-Host "⚠️  Could not disable service: $_" -ForegroundColor Yellow
}

# Verify
Write-Host "`n📊 Current status:" -ForegroundColor Cyan
Get-Service -Name "postgresql-x64-17" | Select-Object Name, Status, StartType | Format-Table

Write-Host "✅ Done! Local PostgreSQL is now stopped and disabled." -ForegroundColor Green
Write-Host "   Docker PostgreSQL will be used instead (port 5433)" -ForegroundColor Cyan
