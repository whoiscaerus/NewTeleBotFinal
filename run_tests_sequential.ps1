# Run each test file sequentially and log results
$testFiles = @(
    "backend/tests/backtest/test_backtest_adapters.py",
    "backend/tests/backtest/test_backtest_runner.py",
    "backend/tests/test_ab_testing.py",
    "backend/tests/test_alerts.py",
    "backend/tests/test_audit.py",
    "backend/tests/test_auth.py",
    "backend/tests/test_cache.py",
    "backend/tests/test_copy.py",
    "backend/tests/test_data_pipeline.py"
)

$resultsFile = "c:\Users\FCumm\NewTeleBotFinal\test_results.log"
"" | Out-File $resultsFile

$totalPassed = 0
$totalFailed = 0
$failedFiles = @()

foreach ($testFile in $testFiles) {
    Write-Host "Running: $testFile" -ForegroundColor Cyan
    "==========================================" | Add-Content $resultsFile
    "Testing: $testFile" | Add-Content $resultsFile
    "Started: $(Get-Date)" | Add-Content $resultsFile
    
    $output = & .\.venv\Scripts\python.exe -m pytest $testFile -q --tb=no --timeout=10 2>&1
    $exitCode = $LASTEXITCODE
    
    if ($exitCode -eq 0) {
        Write-Host "✅ PASSED" -ForegroundColor Green
        "Status: PASSED" | Add-Content $resultsFile
        $totalPassed++
    } else {
        Write-Host "❌ FAILED" -ForegroundColor Red
        "Status: FAILED" | Add-Content $resultsFile
        $failedFiles += $testFile
        $totalFailed++
    }
    
    $output | Add-Content $resultsFile
    "Completed: $(Get-Date)" | Add-Content $resultsFile
    ""  | Add-Content $resultsFile
    
    Start-Sleep -Milliseconds 100
}

Write-Host "`nSUMMARY:" -ForegroundColor Yellow
Write-Host "Passed: $totalPassed" -ForegroundColor Green
Write-Host "Failed: $totalFailed" -ForegroundColor Red

if ($failedFiles.Count -gt 0) {
    Write-Host "`nFailed files:" -ForegroundColor Red
    $failedFiles | ForEach-Object { Write-Host "  - $_" }
}

"`n================ SUMMARY ================" | Add-Content $resultsFile
"Total Passed: $totalPassed" | Add-Content $resultsFile
"Total Failed: $totalFailed" | Add-Content $resultsFile
"Failed Files: $($failedFiles -join ', ')" | Add-Content $resultsFile

Write-Host "`nResults saved to: $resultsFile"
