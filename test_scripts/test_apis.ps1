# Test API Endpoints for SOC Analyzer

Write-Host "`n=== TESTING API ENDPOINTS ===" -ForegroundColor Cyan

# Test 1: Backend health check
Write-Host "`n1. Testing backend root..." -ForegroundColor Yellow
try {
    $root = Invoke-RestMethod -Uri "http://localhost:8000/" -Method Get
    Write-Host "✓ Backend is running: $($root.message)" -ForegroundColor Green
} catch {
    Write-Host "✗ Backend not responding!" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
}

# Test 2: Get scans list
Write-Host "`n2. Testing GET /history (scans list)..." -ForegroundColor Yellow
try {
    $history = Invoke-RestMethod -Uri "http://localhost:8000/history" -Method Get
    Write-Host "✓ Found $($history.Count) scans" -ForegroundColor Green
    if ($history.Count -gt 0) {
        $history | Select-Object id, filename, company | Format-Table
    } else {
        Write-Host "! No scans found in history" -ForegroundColor Yellow
    }
} catch {
    Write-Host "✗ Failed to fetch history!" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
}

# Test 3: Get scan #26
Write-Host "`n3. Testing GET /report/26..." -ForegroundColor Yellow
try {
    $report = Invoke-RestMethod -Uri "http://localhost:8000/report/26" -Method Get
    Write-Host "✓ Scan ID: $($report.scan_id)" -ForegroundColor Green
    Write-Host "  Company: $($report.company)" -ForegroundColor Gray
    Write-Host "  Product: $($report.product)" -ForegroundColor Gray
    Write-Host "  Controls: $($report.controls.Count)" -ForegroundColor Gray
    Write-Host "  CUECs: $($report.cuecs.Count)" -ForegroundColor Gray
    Write-Host "  SubOrgs: $($report.subservice_orgs.Count)" -ForegroundColor Gray
    
    # Check first control
    if ($report.controls.Count -gt 0) {
        $ctrl = $report.controls[0]
        Write-Host "`n  First Control:" -ForegroundColor Gray
        Write-Host "    ID: $($ctrl.control_id)" -ForegroundColor Gray
        Write-Host "    Confidence: $($ctrl.control_confidence)" -ForegroundColor Gray
        Write-Host "    Page Refs: $($ctrl.control_page_refs)" -ForegroundColor Gray
        Write-Host "    Merged To: $($ctrl.merged_to_control_id)" -ForegroundColor Gray
        Write-Host "    Verification Metadata: $(if ($ctrl.verification_metadata) {'Present'} else {'Missing'})" -ForegroundColor Gray
        
        # Check for controls with confidence
        $withConfidence = ($report.controls | Where-Object { $null -ne $_.control_confidence }).Count
        Write-Host "`n  Controls with confidence: $withConfidence / $($report.controls.Count)" -ForegroundColor Gray
        
        # Check for controls with page refs
        $withPageRefs = ($report.controls | Where-Object { $null -ne $_.control_page_refs }).Count
        Write-Host "  Controls with page_refs: $withPageRefs / $($report.controls.Count)" -ForegroundColor Gray
        
        # Check for merged controls
        $merged = ($report.controls | Where-Object { $null -ne $_.merged_to_control_id }).Count
        Write-Host "  Merged controls (should be 0 if filter working): $merged" -ForegroundColor Gray
    }
    
} catch {
    Write-Host "✗ Failed to fetch report!" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
}

# Test 4: Check for duplicate control IDs
Write-Host "`n4. Checking for duplicate control IDs..." -ForegroundColor Yellow
try {
    if ($report -and $report.controls) {
        $duplicates = $report.controls | Group-Object control_id | Where-Object {$_.Count -gt 1}
        if ($duplicates.Count -gt 0) {
            Write-Host "! Found $($duplicates.Count) control IDs with duplicates:" -ForegroundColor Yellow
            $duplicates | Select-Object Name, Count | Format-Table
        } else {
            Write-Host "✓ No duplicate control IDs found (or all merged)" -ForegroundColor Green
        }
    }
} catch {
    Write-Host "Could not check duplicates" -ForegroundColor Gray
}

Write-Host "`n=== TEST COMPLETE ===" -ForegroundColor Cyan
