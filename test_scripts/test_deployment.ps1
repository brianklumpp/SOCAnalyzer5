# SOCAnalyzer v1.0.13 Deployment Test Script
# Tests: Docker services, database schema, certificates, configs

param([switch]$Verbose)

$ErrorActionPreference = "Continue"
$PassCount = 0
$FailCount = 0
$WarnCount = 0

function Test-Pass { param([string]$msg) Write-Host "  ??? $msg" -ForegroundColor Green; $script:PassCount++ }
function Test-Fail { param([string]$msg) Write-Host "  ??? $msg" -ForegroundColor Red; $script:FailCount++ }
function Test-Warn { param([string]$msg) Write-Host "  ??? $msg" -ForegroundColor Yellow; $script:WarnCount++ }
function Test-Info { param([string]$msg) if ($Verbose) { Write-Host "    ??? $msg" -ForegroundColor Gray } }
function Test-Header { param([string]$msg) Write-Host "`n========================================"  -ForegroundColor Cyan; Write-Host "  $msg" -ForegroundColor Cyan; Write-Host "========================================" -ForegroundColor Cyan }

# Test 1: Docker Services
Test-Header "Docker Service Health"
$containers = docker ps -a --format json | ConvertFrom-Json
$expected = @('socanalyzer-backend','socanalyzer-frontend','socanalyzer-postgres','socanalyzer-redis','socanalyzer-dns-cache')
foreach ($name in $expected) {
    $c = $containers | Where-Object { $_.Names -eq $name }
    if ($c -and $c.State -eq 'running') { Test-Pass "$name is running" }
    elseif ($c) { Test-Fail "$name exists but not running ($($c.State))" }
    else { Test-Fail "$name container not found" }
}

# Test 2: Health Checks
Test-Header "Container Health Checks"
$containers | ForEach-Object {
    if ($_.Status -match 'healthy') { Test-Pass "$($_.Names) is healthy" }
    elseif ($_.Status -match 'unhealthy') { Test-Fail "$($_.Names) is unhealthy" }
    elseif ($_.Status -match 'starting') { Test-Warn "$($_.Names) still starting" }
    else { Test-Info "$($_.Names) has no healthcheck" }
}

# Test 3: Network Connectivity
Test-Header "Network Connectivity"
# Find the actual network name (could be socanalyzer-network or socanalyzer_socanalyzer-network)
$networks = docker network ls --format "{{.Name}}" | Where-Object { $_ -match 'socanalyzer-network' }
if ($networks) {
    $netName = $networks | Select-Object -First 1
    $network = docker network inspect $netName 2>$null | ConvertFrom-Json
    Test-Pass "Network exists: $netName"
    $subnet = $network.IPAM.Config[0].Subnet
    if ($subnet -eq '172.20.0.0/16') { Test-Pass "Subnet correct: $subnet" }
    else { Test-Fail "Subnet wrong: $subnet" }
    
    $expectedIPs = @{'socanalyzer-dns-cache'='172.20.0.2';'socanalyzer-postgres'='172.20.0.3';'socanalyzer-redis'='172.20.0.4'}
    foreach ($name in $expectedIPs.Keys) {
        $info = docker inspect $name 2>$null | ConvertFrom-Json
        $actualNetName = ($info.NetworkSettings.Networks | Get-Member -MemberType NoteProperty).Name
        $ip = $info.NetworkSettings.Networks.$actualNetName.IPAddress
        if ($ip -eq $expectedIPs[$name]) { Test-Pass "$name has correct IP: $ip" }
        else { Test-Fail "$name has wrong IP: $ip (expected $($expectedIPs[$name]))" }
    }
} else {
    Test-Fail "socanalyzer-network not found"
}

# Test 4: Database Schema
Test-Header "Database Schema"
$dbCheck = docker exec socanalyzer-postgres psql -U soc2_analyzer -d soc2analyzer -c "\d scan" 2>&1
if ($dbCheck -match 'company') { Test-Pass "scan.company column exists" }
else { Test-Fail "scan.company column missing" }

@('id','pdf_filename','report_type','elapsed_seconds','toc_page_offset') | ForEach-Object {
    if ($dbCheck -match $_) { Test-Pass "scan.$_ column exists" }
    else { Test-Fail "scan.$_ column missing" }
}

$migration = docker exec socanalyzer-postgres psql -U soc2_analyzer -d soc2analyzer -c "SELECT version_num FROM alembic_version;" 2>&1
$migVersion = ($migration -split "`n")[2].Trim()
if ($migration -match '20251210_add_all_missing_columns') { 
    Test-Pass "Migrations up to date: $migVersion" 
} elseif ($dbCheck -match 'company') {
    Test-Pass "Database schema current (upgraded from $migVersion)"
} else { 
    Test-Fail "Migration outdated: $migVersion (expected 20251210_add_all_missing_columns or company column present)" 
}

# Test 5: Certificates
Test-Header "Certificate Configuration"
docker exec socanalyzer-backend test -f /certs/corp-ca-bundle.pem 2>$null
if ($LASTEXITCODE -eq 0) {
    Test-Pass "Certificate file exists"
    $size = docker exec socanalyzer-backend stat -c%s /certs/corp-ca-bundle.pem 2>$null
    if ($size -gt 1000) { Test-Pass "Certificate size valid: $size bytes" }
    else { Test-Warn "Certificate seems small: $size bytes" }
} else { Test-Warn "Certificate not found (will use system CAs)" }

$logs = docker logs socanalyzer-backend --tail 100 2>&1
if ($logs -match 'Using corporate CA bundle') { Test-Pass "Backend using corporate CA" }
elseif ($logs -match 'will use system CAs') { Test-Warn "Backend using system CAs" }

# Test 6: Docker Compose Config
Test-Header "Docker Compose Configuration"
if (Test-Path 'docker-compose.yml') {
    Test-Pass "docker-compose.yml exists"
    $yml = Get-Content 'docker-compose.yml' -Raw
    if ($yml -match 'dns-cache:') { Test-Pass "dns-cache service defined" }
    else { Test-Fail "dns-cache missing" }
    if ($yml -match 'healthcheck:') { Test-Pass "dns-cache has healthcheck" }
    else { Test-Fail "healthcheck missing" }
    if ($yml -match '172\.20\.0\.2') { Test-Pass "healthcheck IP correct" }
    else { Test-Fail "healthcheck IP wrong" }
    if ($yml -match 'start_period:\s*10s') { Test-Pass "start_period is 10s" }
    else { Test-Warn "start_period not 10s" }
} else { Test-Fail "docker-compose.yml not found" }

# Test 7: Environment Variables
Test-Header "Environment Variables"
if (Test-Path '.env') {
    Test-Pass ".env exists"
    $env = Get-Content '.env' -Raw
    @('POSTGRES_DB','POSTGRES_USER','POSTGRES_PASSWORD') | ForEach-Object {
        if ($env -match "$_=") { Test-Pass "$_ is set" }
        else { Test-Fail "$_ missing" }
    }
    @('REDIS_HOST','POSTGRES_HOST') | ForEach-Object {
        if ($env -match "$_=") { Test-Pass "$_ is set" }
        else { Test-Info "$_ not in .env (using docker-compose defaults)" }
    }
} else { Test-Warn ".env not found (using defaults)" }

$backendEnv = docker exec socanalyzer-backend printenv 2>&1
if ($backendEnv -match 'DATAIKU_DSS_HOST') { Test-Pass "Backend has DATAIKU_DSS_HOST" }
else { Test-Warn "DATAIKU_DSS_HOST not set" }
if ($backendEnv -match 'POSTGRES_HOST') { Test-Pass "Backend has POSTGRES_HOST" }
else { Test-Info "POSTGRES_HOST uses docker-compose default" }

# Test 8: API Endpoints
Test-Header "API Endpoints"
try {
    $r = Invoke-WebRequest -Uri 'http://localhost:8000/docs' -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
    if ($r.StatusCode -eq 200) { Test-Pass "Backend API responding" }
    else { Test-Fail "Backend API returned $($r.StatusCode)" }
} catch { Test-Fail "Backend API not responding: $_" }

try {
    $r = Invoke-WebRequest -Uri 'http://localhost:8000/settings' -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
    if ($r.StatusCode -eq 200) { Test-Pass "Backend /settings responding" }
    else { Test-Fail "Backend /settings returned $($r.StatusCode)" }
} catch { Test-Fail "Backend /settings not responding" }

try {
    $r = Invoke-WebRequest -Uri 'http://localhost:80' -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
    if ($r.StatusCode -eq 200) { Test-Pass "Frontend responding on port 80" }
    else { Test-Fail "Frontend returned $($r.StatusCode)" }
} catch { 
    try {
        $r = Invoke-WebRequest -Uri 'http://localhost:3000' -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        if ($r.StatusCode -eq 200) { Test-Pass "Frontend responding on port 3000" }
    } catch { Test-Fail "Frontend not responding on port 80 or 3000" }
}

# Test 9: DNS Resolution
Test-Header "DNS Resolution"
$dns = docker exec socanalyzer-dns-cache nslookup google.com 172.20.0.2 2>&1
if ($dns -match 'Address:' -or $dns -match 'answer:') { Test-Pass "DNS cache can resolve domains" }
else { Test-Fail "DNS cache cannot resolve" }

$backendDns = docker exec socanalyzer-backend nslookup google.com 172.20.0.2 2>&1
if ($backendDns -match 'Address:') { Test-Pass "Backend can use DNS cache" }
else { Test-Warn "Backend cannot use DNS cache" }

# Test 10: Volumes
Test-Header "Volume Mounts"
$vols = docker volume ls --format json | ConvertFrom-Json
if ($vols.Name -contains 'postgres_data' -or $vols -match 'postgres_data') { Test-Pass "postgres_data volume exists" }
else { Test-Fail "postgres_data volume not found" }

$dirs = docker exec socanalyzer-backend ls -la /app/data 2>&1
if ($dirs -match 'output') { Test-Pass "Backend has /app/data/output" }
else { Test-Fail "Backend missing /app/data/output" }

# Summary
Test-Header "Test Summary"
$total = $PassCount + $FailCount + $WarnCount
Write-Host ""
Write-Host "  Total: $total" -ForegroundColor Cyan
Write-Host "  ??? Passed: $PassCount" -ForegroundColor Green
Write-Host "  ??? Failed: $FailCount" -ForegroundColor Red
Write-Host "  ??? Warnings: $WarnCount" -ForegroundColor Yellow
Write-Host ""

if ($FailCount -eq 0 -and $WarnCount -eq 0) {
    Write-Host "???? All tests passed! Deployment is healthy." -ForegroundColor Green
    exit 0
} elseif ($FailCount -eq 0) {
    Write-Host "??? All critical tests passed. Some warnings present." -ForegroundColor Yellow
    exit 0
} else {
    Write-Host "??? Deployment has issues that need attention." -ForegroundColor Red
    exit 1
}
