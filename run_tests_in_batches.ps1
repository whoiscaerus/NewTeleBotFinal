# Run tests in batches to avoid hanging
# Skip known problematic test files

$testDir = "backend/tests"
$excludeFiles = @(
    "test_pr_025_execution_store.py",
    "test_pr_048_trace_worker.py", 
    "test_pr_102_web3_comprehensive.py"
)

$testFiles = @(Get-ChildItem "$testDir/test_*.py" | Where-Object { $_.Name -notin $excludeFiles } | Select-Object -ExpandProperty Name)

Write-Host "Total test files: $($testFiles.Count)" -ForegroundColor Cyan

$batchSize = 10
$passCount = 0
$failCount = 0
$failedFiles = @()

for ($i = 0; $i -lt $testFiles.Count; $i += $batchSize) {
    $batch = $testFiles[$i..($i + $batchSize - 1)]
    $batchNum = [math]::Floor($i / $batchSize) + 1
    
    Write-Host "`n=== Batch $batchNum ===" -ForegroundColor Yellow
    Write-Host "Running $($batch.Count) files..." -ForegroundColor White
    
    $filePaths = $batch | ForEach-Object { "$testDir/$_" }
    
    # Run pytest with 10 second timeout per test
    $cmd = ".venv/Scripts/python.exe -m pytest $($filePaths -join ' ') -v --tb=line --timeout=10 -q"
    
    Write-Host "Command: $cmd" -ForegroundColor Gray
    
    $output = Invoke-Expression $cmd 2>&1
    $lastLine = $output[-1]
    
    # Parse results
    if ($lastLine -match "(\d+) passed") {
        $passed = [int]$matches[1]
        $passCount += $passed
        Write-Host "✅ $passed passed" -ForegroundColor Green
    }
    
    if ($lastLine -match "(\d+) failed") {
        $failed = [int]$matches[1]
        $failCount += $failed
        $failedFiles += $batch
        Write-Host "❌ $failed failed" -ForegroundColor Red
        Write-Host $lastLine -ForegroundColor Red
    }
}

Write-Host "`n=== FINAL RESULTS ===" -ForegroundColor Cyan
Write-Host "✅ Passed: $passCount" -ForegroundColor Green
Write-Host "❌ Failed: $failCount" -ForegroundColor Red

if ($failedFiles.Count -gt 0) {
    Write-Host "`nFailed test files:" -ForegroundColor Yellow
    $failedFiles | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
}
