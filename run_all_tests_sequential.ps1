# Run EACH test file separately - ALL 236 files
# Logs results to CSV for easy analysis

$testDir = "c:\Users\FCumm\NewTeleBotFinal\backend\tests"
$resultsFile = "c:\Users\FCumm\NewTeleBotFinal\ALL_TEST_RESULTS.csv"
$summaryFile = "c:\Users\FCumm\NewTeleBotFinal\TEST_SUMMARY.txt"

# Get ALL test files
$testFiles = Get-ChildItem -Path $testDir -Filter "test_*.py" -Recurse | Sort-Object FullName

Write-Host "Found $($testFiles.Count) test files"
Write-Host "Running each file separately..." -ForegroundColor Cyan

# Clear previous results
"TestFile,Status,Duration,TestsCount,Passed,Failed,Skipped,Errors" | Out-File $resultsFile

$totalFiles = 0
$passedFiles = 0
$failedFiles = 0
$hangingFiles = @()
$failedList = @()

foreach ($file in $testFiles) {
    $totalFiles++
    $relativePath = $file.FullName -replace [regex]::Escape("$testDir\"), ""
    
    Write-Host "[$totalFiles/$($testFiles.Count)] $relativePath" -ForegroundColor Yellow
    
    $startTime = Get-Date
    
    # Run pytest with 15-second timeout per file
    $output = & .\.venv\Scripts\python.exe -m pytest "$($file.FullName)" -q --tb=no --timeout=10 2>&1
    $exitCode = $LASTEXITCODE
    
    $duration = (Get-Date) - $startTime
    $durationSeconds = [math]::Round($duration.TotalSeconds, 2)
    
    if ($exitCode -eq 0) {
        Write-Host "  ✅ PASSED ($durationSeconds`s)" -ForegroundColor Green
        $passedFiles++
        $status = "PASSED"
    } else {
        Write-Host "  ❌ FAILED ($durationSeconds`s)" -ForegroundColor Red
        $failedFiles++
        $failedList += $relativePath
        $status = "FAILED"
    }
    
    # Parse output for test counts
    $outputStr = $output | Out-String
    if ($outputStr -match "(\d+) passed") {
        $passedCount = $matches[1]
    } else {
        $passedCount = "0"
    }
    
    if ($outputStr -match "(\d+) failed") {
        $failedCount = $matches[1]
    } else {
        $failedCount = "0"
    }
    
    if ($outputStr -match "(\d+) skipped") {
        $skippedCount = $matches[1]
    } else {
        $skippedCount = "0"
    }
    
    if ($outputStr -match "(\d+) error") {
        $errorCount = $matches[1]
    } else {
        $errorCount = "0"
    }
    
    # Estimate total tests in file
    $totalTests = [int]$passedCount + [int]$failedCount + [int]$skippedCount + [int]$errorCount
    if ($totalTests -eq 0) { $totalTests = "?" }
    
    "$relativePath,$status,$durationSeconds,$totalTests,$passedCount,$failedCount,$skippedCount,$errorCount" | Add-Content $resultsFile
}

# Write summary
$summaryText = @"
====== TEST EXECUTION SUMMARY ======
Total Test Files: $totalFiles
Passed Files: $passedFiles
Failed Files: $failedFiles
Success Rate: $([math]::Round(($passedFiles / $totalFiles) * 100, 1))%

FAILED TEST FILES:
$($failedList -join "`n")

Results saved to: $resultsFile
"@

$summaryText | Out-File $summaryFile
$summaryText | Write-Host -ForegroundColor Cyan

Write-Host "`nDetailed results in: $resultsFile"
Write-Host "Summary in: $summaryFile"
