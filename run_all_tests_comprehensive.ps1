# Comprehensive Test Suite Runner with Live Tracking
# Purpose: Run all tests 1 file at a time and collect metrics

param(
    [string]$OutputDir = ".",
    [bool]$Verbose = $true
)

$timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$logFile = "$OutputDir\ALL_TEST_EXECUTION_$timestamp.log"
$csvFile = "$OutputDir\ALL_TEST_RESULTS_$timestamp.csv"
$summaryFile = "$OutputDir\TEST_SUMMARY_$timestamp.txt"

# Initialize files
"Test Execution Log - $timestamp" | Out-File -FilePath $logFile -Force
"TestFile,Total,Passed,Failed,Skipped,Duration,Status" | Out-File -FilePath $csvFile -Force

# Arrays to track results
$results = @()
$totalStats = @{
    Files = 0
    Total = 0
    Passed = 0
    Failed = 0
    Skipped = 0
}

# Get all test files
$testFiles = Get-ChildItem -Path "backend/tests" -Name "test_*.py" -File | Sort-Object

Write-Host "=== STARTING COMPREHENSIVE TEST SUITE ===" -ForegroundColor Cyan
Write-Host "Total test files found: $($testFiles.Count)" -ForegroundColor Cyan
Write-Host "Output: $logFile" -ForegroundColor Cyan
Write-Host "CSV: $csvFile" -ForegroundColor Cyan
Write-Host ""

$currentFile = 0
$startTime = Get-Date

foreach ($testFile in $testFiles) {
    $currentFile++
    $filePath = "backend/tests/$testFile"
    $percentComplete = [math]::Round(($currentFile / $testFiles.Count) * 100)
    
    # Print progress header
    $progressMsg = "[$currentFile/$($testFiles.Count) - $percentComplete%] Testing: $testFile"
    Write-Host $progressMsg -ForegroundColor Yellow
    
    # Run the test
    $testStartTime = Get-Date
    $output = & .venv/Scripts/python.exe -m pytest $filePath -q --tb=no 2>&1
    $testEndTime = Get-Date
    $duration = ($testEndTime - $testStartTime).TotalSeconds
    
    # Parse output to extract statistics
    $passed = 0
    $failed = 0
    $skipped = 0
    $total = 0
    $status = "UNKNOWN"
    
    # Look for the summary line (e.g., "33 passed in 4.88s")
    $summaryMatch = $output | Select-String -Pattern '(\d+)\s+passed|(\d+)\s+failed|(\d+)\s+skipped' -AllMatches
    
    foreach ($line in $output) {
        if ($line -match '(\d+)\s+passed') {
            $passed = [int]$matches[1]
        }
        if ($line -match '(\d+)\s+failed') {
            $failed = [int]$matches[1]
        }
        if ($line -match '(\d+)\s+skipped') {
            $skipped = [int]$matches[1]
        }
    }
    
    $total = $passed + $failed + $skipped
    
    if ($failed -eq 0 -and $total -gt 0) {
        $status = "PASS"
        $statusColor = "Green"
    } elseif ($failed -gt 0) {
        $status = "FAIL"
        $statusColor = "Red"
    } else {
        $status = "SKIP"
        $statusColor = "Gray"
    }
    
    # Display result
    $resultMsg = "  $status | P:$passed F:$failed S:$skipped (${duration}s)"
    Write-Host $resultMsg -ForegroundColor $statusColor
    
    # Update totals
    $totalStats.Files++
    $totalStats.Total += $total
    $totalStats.Passed += $passed
    $totalStats.Failed += $failed
    $totalStats.Skipped += $skipped
    
    # Append to CSV
    "$testFile,$total,$passed,$failed,$skipped,$([math]::Round($duration, 2)),$status" | Add-Content -Path $csvFile
    
    # Append to log
    "[$currentFile/$($testFiles.Count)] $testFile - Passed: $passed, Failed: $failed, Skipped: $skipped, Duration: ${duration}s, Status: $status" | Add-Content -Path $logFile
    
    # Store result object
    $results += [PSCustomObject]@{
        File = $testFile
        Total = $total
        Passed = $passed
        Failed = $failed
        Skipped = $skipped
        Duration = $duration
        Status = $status
    }
}

$totalTime = (Get-Date) - $startTime

# Generate summary
Write-Host ""
Write-Host "=== TEST SUITE COMPLETE ===" -ForegroundColor Cyan
Write-Host "Total Files: $($totalStats.Files)" -ForegroundColor Cyan
Write-Host "Total Tests: $($totalStats.Total)" -ForegroundColor Cyan
Write-Host "Total Passed: $($totalStats.Passed)" -ForegroundColor Green
Write-Host "Total Failed: $($totalStats.Failed)" -ForegroundColor Red
Write-Host "Total Skipped: $($totalStats.Skipped)" -ForegroundColor Gray
Write-Host "Total Duration: $([math]::Round($totalTime.TotalMinutes, 2)) minutes" -ForegroundColor Cyan

# Calculate pass rate
$passRate = if ($totalStats.Total -gt 0) { 
    [math]::Round(($totalStats.Passed / $totalStats.Total) * 100, 2) 
} else { 
    0 
}

Write-Host "Pass Rate: $passRate%" -ForegroundColor Cyan
Write-Host ""

# Write summary file
@"
COMPREHENSIVE TEST SUITE SUMMARY
Generated: $timestamp
Total Duration: $([math]::Round($totalTime.TotalMinutes, 2)) minutes

OVERALL STATISTICS:
- Total Test Files: $($totalStats.Files)
- Total Tests: $($totalStats.Total)
- Passed: $($totalStats.Passed)
- Failed: $($totalStats.Failed)
- Skipped: $($totalStats.Skipped)
- Pass Rate: $passRate%

FAILED TEST FILES:
"@ | Out-File -FilePath $summaryFile -Force

$failedFiles = $results | Where-Object { $_.Status -eq "FAIL" } | Sort-Object -Property Failed -Descending
if ($failedFiles) {
    $failedFiles | ForEach-Object {
        "$($_.File): $($_.Failed) failures" | Add-Content -Path $summaryFile
    }
} else {
    "None!" | Add-Content -Path $summaryFile
}

# Add top failing files for fixing priority
@"

TOP PRIORITY FIXES (Most Failures):
"@ | Add-Content -Path $summaryFile

$failedFiles | Select-Object -First 10 | ForEach-Object {
    "$($_.File): $($_.Failed) failures" | Add-Content -Path $summaryFile
}

Write-Host "Summary saved to: $summaryFile" -ForegroundColor Cyan
Write-Host "Full CSV saved to: $csvFile" -ForegroundColor Cyan
