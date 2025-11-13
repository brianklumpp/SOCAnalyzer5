# Copy data from local PostgreSQL to Docker PostgreSQL

Write-Host "📋 Data Migration: Local PostgreSQL → Docker PostgreSQL" -ForegroundColor Cyan
Write-Host ""

# Stop Docker PostgreSQL temporarily
Write-Host "1️⃣  Stopping Docker containers..." -ForegroundColor Yellow
docker-compose down

# Backup local database
Write-Host "`n2️⃣  Backing up local database..." -ForegroundColor Yellow
$backupFile = "database_backup/migrate_$(Get-Date -Format 'yyyyMMdd_HHmmss').sql"
docker run --rm `
    -v "${PWD}/database_backup:/backup" `
    --network host `
    postgres:15-alpine `
    pg_dump -h host.docker.internal -p 5432 -U soc2_analyzer -d soc2analyzer -F p -f "/backup/$(Split-Path $backupFile -Leaf)"

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Backup failed!" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Backup saved to: $backupFile" -ForegroundColor Green

# Start Docker with exposed PostgreSQL port
Write-Host "`n3️⃣  Starting Docker containers..." -ForegroundColor Yellow
docker-compose up -d
Start-Sleep -Seconds 10

# Restore to Docker PostgreSQL
Write-Host "`n4️⃣  Restoring to Docker PostgreSQL..." -ForegroundColor Yellow
Get-Content $backupFile | docker exec -i socanalyzer-postgres psql -U soc2_analyzer -d soc2analyzer

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n✅ Migration complete!" -ForegroundColor Green
    Write-Host "`n📊 Verifying data..." -ForegroundColor Cyan
    docker exec socanalyzer-postgres psql -U soc2_analyzer -d soc2analyzer -c "SELECT COUNT(*) as scan_count FROM scan;"
} else {
    Write-Host "`n❌ Restore failed!" -ForegroundColor Red
}
