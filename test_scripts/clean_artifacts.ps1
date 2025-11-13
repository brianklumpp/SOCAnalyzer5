$base = Split-Path -Parent $PSScriptRoot
# $base points to SOCAnalyzer5
$root = $base
Write-Host "Root: $root"
# Remove JSON artifacts
$files = @(
  'data/json/control_result.json',
  'data/json/cuec_result.json',
  'data/json/subservice_orgs_result.json',
  'data/json/subservice_orgs_result_postprocessed.json',
  'data/json/product_result.json',
  'data/json/auditor_result.json',
  'data/json/company_result.json',
  'data/json/report_date_result.json',
  'data/json/coverage_period_result.json',
  'data/json/combined_result.json',
  'data/json/section_results.json'
)
foreach ($rel in $files) {
  $path = Join-Path $root $rel
  if (Test-Path $path) {
    try {
      Remove-Item -Force $path -ErrorAction Stop
      Write-Host "Removed $rel"
    } catch {
      $msg = $_.Exception.Message
      Write-Host ("Failed to remove " + $rel + ": " + $msg)
    }
  }
}
# Remove output text
$out = Join-Path $root 'data/output/output.txt'
if (Test-Path $out) {
  try { Remove-Item -Force $out; Write-Host "Removed data/output/output.txt" } catch {}
}
# Truncate logs
$logs = Join-Path $root 'data/logs'
if (Test-Path $logs) {
  Get-ChildItem $logs -File | ForEach-Object {
    try { Set-Content -Path $_.FullName -Value $null -ErrorAction Stop; Write-Host "Truncated log: $($_.Name)" } catch {}
  }
}
Write-Host "Cleanup complete."