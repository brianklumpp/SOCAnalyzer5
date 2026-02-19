# Fix hung job by marking it complete
$jobId = "52c5bca2-ab3a-420b-83d4-a8f42312d9a3"

# Get current job
$json = docker exec socanalyzer-redis redis-cli GET "job:$jobId"
Write-Host "Current status: $json"

# Parse and modify
$job = $json | ConvertFrom-Json
$job.done = $true
$job.progress = 100
$job.status = "Complete"

# Convert back to JSON and write to temp file
$newJson = ($job | ConvertTo-Json -Compress -Depth 10)
$newJson | Out-File -FilePath ".\temp_job_update.txt" -Encoding ASCII -NoNewline

# Read back and set in Redis
$content = Get-Content ".\temp_job_update.txt" -Raw
docker exec socanalyzer-redis redis-cli SET "job:$jobId" $content

Write-Host "`nJob updated. Verifying..."
docker exec socanalyzer-redis redis-cli GET "job:$jobId" | ConvertFrom-Json | Select-Object done, progress, status
