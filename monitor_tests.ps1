# PowerShell script to monitor test execution in real-time with detailed logging
param(
    [int]$CheckInterval = 5,
    [int]$MaxWaitMinutes = 60
)

$OutputFile = "full_test_run.log"
$StartTime = Get-Date

# Clear any previous run
if (Test-Path $OutputFile) {
    Remove-Item $OutputFile -Force
}

Write-Host "Starting comprehensive test run monitoring..."
Write-Host "Output file: $OutputFile"
Write-Host "Check interval: ${CheckInterval}s"
Write-Host "Starting pytest job..."

# Start the job
$job = Start-Job -ScriptBlock {
    cd 'c:\Users\FCumm\NewTeleBotFinal'
    .\.venv\Scripts\python.exe -m pytest `
        backend/tests/ `
        --ignore=backend/tests/test_pr_025_execution_store.py `
        --ignore=backend/tests/test_pr_048_trace_worker.py `
        --ignore=backend/tests/test_pr_102_web3_comprehensive.py `
        -v --tb=no --timeout=10 `
        2>&1
}

Write-Host "Job started with ID: $($job.Id)"
Write-Host ""

$lastLineCount = 0
$startFileSize = 0

# Monitor the job
while ($job.State -eq "Running") {
    Start-Sleep -Seconds $CheckInterval
    
    $output = Receive-Job -Id $job.Id -Keep
    if ($output) {
        $lineCount = @($output).Count
        $outputText = $output -join "`n"
        $outputText | Out-File -FilePath $OutputFile -Append
        
        # Show progress every interval
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Output lines: $lineCount | File size: $((Get-Item $OutputFile -ErrorAction SilentlyContinue).Length / 1KB)KB | Duration: $((Get-Date) - $StartTime | Select -ExpandProperty Minutes)m $(((Get-Date) - $StartTime).Seconds)s"
        
        # Show last test result
        $lastLines = $output | Select-Object -Last 3
        if ($lastLines) {
            foreach ($line in $lastLines) {
                if ($line -match "PASSED|FAILED|ERROR|TIMEOUT") {
                    Write-Host "  → $line" -ForegroundColor Cyan
                }
            }
        }
        
        $lastLineCount = $lineCount
    }
    
    # Check timeout
    if (((Get-Date) - $StartTime).Minutes -gt $MaxWaitMinutes) {
        Write-Host "Timeout! Stopping job after $MaxWaitMinutes minutes"
        Stop-Job -Id $job.Id
        break
    }
}

Write-Host ""
Write-Host "Job completed with state: $($job.State)"
Write-Host "Retrieving final output..."

# Get all remaining output
$finalOutput = Receive-Job -Id $job.Id
if ($finalOutput) {
    $finalOutput | Out-File -FilePath $OutputFile -Append
}

# Display final summary
Write-Host ""
Write-Host "=== FINAL TEST RESULTS ==="
$content = Get-Content $OutputFile -Raw
$summaryMatch = $content -match '=+\s+(\d+)\s+passed.*?in\s+[\d.]+s'
if ($MATCHES) {
    Write-Host $MATCHES[0] -ForegroundColor Green
}

Write-Host ""
Write-Host "Full output saved to: $OutputFile"
Write-Host "Total duration: $((Get-Date) - $StartTime | Select -ExpandProperty Minutes)m $(((Get-Date) - $StartTime).Seconds)s"

# Extract key stats
Write-Host ""
Write-Host "=== SUMMARY STATS ==="
$passCount = ($content | Select-String "PASSED" -AllMatches).Matches.Count
$failCount = ($content | Select-String "FAILED" -AllMatches).Matches.Count
$errorCount = ($content | Select-String "ERROR" -AllMatches).Matches.Count
$timeoutCount = ($content | Select-String "TIMEOUT" -AllMatches).Matches.Count

Write-Host "Passed: $passCount"
Write-Host "Failed: $failCount"
Write-Host "Errors: $errorCount"
Write-Host "Timeouts: $timeoutCount"

# Show end of file
Write-Host ""
Write-Host "=== LAST 50 LINES OF OUTPUT ==="
Get-Content $OutputFile -Tail 50
