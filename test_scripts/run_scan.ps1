param(
    [Parameter(Mandatory=$true)]
    [string]$PdfPath,
    [int]$PollSeconds = 300
)
$ErrorActionPreference = 'Stop'
if (!(Test-Path $PdfPath)) { throw "PDF not found: $PdfPath" }
Write-Host "Starting scan for: $PdfPath"
# Start job using HttpClient with multipart/form-data (Windows PowerShell compatibility)
Add-Type -AssemblyName System.Net.Http
$client = New-Object System.Net.Http.HttpClient
try {
    $content = New-Object System.Net.Http.MultipartFormDataContent
    $fs = [System.IO.File]::OpenRead($PdfPath)
    try {
        $streamContent = New-Object System.Net.Http.StreamContent($fs)
        $streamContent.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse('application/pdf')
        $filename = [System.IO.Path]::GetFileName($PdfPath)
        $content.Add($streamContent, 'file', $filename)
        $respMsg = $client.PostAsync('http://127.0.0.1:8000/analyze/', $content).Result
        $respText = $respMsg.Content.ReadAsStringAsync().Result
        if (-not $respMsg.IsSuccessStatusCode) { throw "Analyze POST failed: $($respMsg.StatusCode) $respText" }
        $resp = $respText | ConvertFrom-Json
    } finally {
        if ($fs) { $fs.Dispose() }
    }
} finally {
    if ($content) { $content.Dispose() }
    if ($client) { $client.Dispose() }
}
$job = $resp.job_id
if (-not $job) { throw "No job_id returned from /analyze/" }
Write-Host "JOB_ID=$job"

# Poll loop
$deadline = (Get-Date).AddSeconds($PollSeconds)
$done = $false
$status = $null
$i = 0
while ((Get-Date) -lt $deadline) {
    try {
        $status = Invoke-RestMethod -Uri ("http://127.0.0.1:8000/analyze/status_min/" + $job) -Method Get
        $prog = if ($status.progress -ne $null) { [int]$status.progress } else { -1 }
        $cnt = if ($status.counts) { $status.counts } else { @{} }
        $ctrl = if ($cnt.control -ne $null) { $cnt.control } else { -1 }
        Write-Host ("poll #$i progress=$prog% controls=$ctrl done=" + ($status.done -eq $true))
        if ($status.error) {
            if ($status.error -eq 'Job not found' -and $status.transient_unavailable) {
                Start-Sleep -Seconds 2
                continue
            } else {
                Write-Host ("Job error: " + $status.error)
                break
            }
        }
        if ($status.done) { $done = $true; break }
    } catch {
        Write-Host ("poll error: " + $_.Exception.Message)
    }
    $i++
    Start-Sleep -Seconds 5
}
if ($done) { Write-Host "Job completed" } else { Write-Host "Job not completed within time budget" }

# Check combined_result.json
$cr = Join-Path (Split-Path -Parent $PSScriptRoot) 'data\json\combined_result.json'
if (Test-Path $cr) {
    $len = (Get-Item $cr).Length
    Write-Host ("combined_result.json bytes=" + $len)
} else {
    Write-Host 'combined_result.json missing'
}
