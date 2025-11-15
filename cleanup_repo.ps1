# Cleanup script - removes unnecessary documentation files
# KEEPS: README.md, CHANGELOG.md, actual code files, docs/ folder structure

# Files to KEEP (whitelist)
$keepFiles = @(
    'README.md',
    'CHANGELOG.md',
    '.gitignore',
    '.env.example',
    'Makefile',
    'pytest.ini',
    'mypy.ini',
    'pyproject.toml',
    'package.json',
    'package-lock.json',
    'jest.config.js',
    'docker-compose.yml',
    '.pre-commit-config.yaml',
    'prometheus.yml',
    'conftest.py'
)

# Patterns to DELETE (these are all session summaries/status files)
$deletePatterns = @(
    '*SESSION*',
    '*SUMMARY*',
    '*COMPLETE*',
    '*STATUS*',
    '*REPORT*',
    '*BANNER*',
    '*FIX*',
    '*QUICK*',
    '*FINAL*',
    '*AUDIT*',
    '*CICD*',
    '*CI_CD*',
    '*VERIFICATION*',
    '*IMPLEMENTATION*',
    '*PHASE*',
    '*PR-*',
    '*PR_*',
    '*COVERAGE*',
    '*EXECUTIVE*',
    '*LINTING*',
    '*MYPY*',
    '*PYTEST*',
    '*GITHUB_ACTIONS*',
    '*DEPLOYMENT*',
    '*DOCUMENTATION*',
    '*MONITOR*',
    '*NEXT*',
    '*READY*',
    '*PRODUCTION*',
    '*FAKEREDIS*',
    '*ASYNC*',
    '*ENCRYPTION*',
    '*APPROVAL*',
    '*AFFILIATE*',
    '*ANALYTICS*',
    '*BOTTOM*',
    '*BUSINESS*',
    '*CODECOV*',
    '*COMMIT*',
    '*COMPREHENSIVE*',
    '*CONTINUATION*',
    '*CRITICAL*',
    '*CURRENT*',
    '*DEPENDENCY*',
    '*DETAILED*',
    '*DEVICE*',
    '*DOCUMENT*',
    '*EXECUTION*',
    '*FEATURE*',
    '*FILES*',
    '*FIXTURE*',
    '*GAP*',
    '*HEADER*',
    '*HOW*',
    '*INFRASTRUCTURE*',
    '*INTEGRATION*',
    '*INTELLIGENT*',
    '*LESSONS*',
    '*LOCAL*',
    '*MAIN*',
    '*MASTER*',
    '*METRICS*',
    '*MT5*',
    '*OPTIONAL*',
    '*PROJECT*',
    '*PUSH*',
    '*QUOTA*',
    '*REALTIME*',
    '*REDIS*',
    '*RESULTS*',
    '*SECURITY*',
    '*SERVICE*',
    '*SOLUTION*',
    '*SUCCESS*',
    '*TEMPLATE*',
    '*TIMEOUT*',
    '*UNIT*',
    '*UNIVERSAL*',
    '*URGENT*',
    '*USER*',
    '*VALIDATION*',
    '*VISUAL*',
    '*WALKFORWARD*',
    '*WEBHOOK*',
    '*YOUR*',
    'test_*.txt',
    'test_*.log',
    '*_results*.txt',
    '*_results*.log',
    '*_results*.csv',
    '*_output*.txt',
    '*_execution*.log',
    'ALL_TEST*',
    'backend_*',
    'combined_*',
    'comprehensive_*',
    'debug_*.py',
    'direct_test.py',
    'err*.txt',
    'error_*.txt',
    'endpoint_*.txt',
    'fix_*.py',
    'full_*.txt',
    'full_*.log',
    'git-error*.txt',
    'htmlcov',
    'live_*.txt',
    'pytest_*.txt',
    'quick_*.txt',
    'ruff_*.txt',
    'run_all_tests*.py',
    'run_all_tests*.ps1',
    'run_tests*.ps1',
    'run_tests*.py',
    'standalone_test*.py',
    'temp_*.txt',
    'unittest*.txt',
    'verify-*.py',
    'check_routes.py',
    'LIVE_TEST_TRACKER.py',
    'PR_024A_TEST_QUICK_REF.py'
)

Write-Host "🧹 Starting cleanup..." -ForegroundColor Cyan
Write-Host ""

$deletedCount = 0
$skippedCount = 0

# Get all files in root directory only
$files = Get-ChildItem -Path . -File -Depth 0

foreach ($file in $files) {
    # Skip if in whitelist
    if ($keepFiles -contains $file.Name) {
        $skippedCount++
        continue
    }

    # Check if matches any delete pattern
    $shouldDelete = $false
    foreach ($pattern in $deletePatterns) {
        if ($file.Name -like $pattern) {
            $shouldDelete = $true
            break
        }
    }

    if ($shouldDelete) {
        Remove-Item $file.FullName -Force
        $deletedCount++
        if ($deletedCount % 50 -eq 0) {
            Write-Host "Deleted $deletedCount files..." -ForegroundColor Yellow
        }
    } else {
        $skippedCount++
    }
}

Write-Host ""
Write-Host "✅ Cleanup complete!" -ForegroundColor Green
Write-Host "   Deleted: $deletedCount files" -ForegroundColor Red
Write-Host "   Kept: $skippedCount files" -ForegroundColor Green
Write-Host ""
Write-Host "Files kept in root:" -ForegroundColor Cyan
Get-ChildItem -Path . -File -Depth 0 | Select-Object -First 20 Name | ForEach-Object { Write-Host "  - $($_.Name)" }

if ((Get-ChildItem -Path . -File -Depth 0).Count -gt 20) {
    Write-Host "  ... and $((Get-ChildItem -Path . -File -Depth 0).Count - 20) more files" -ForegroundColor Gray
}
