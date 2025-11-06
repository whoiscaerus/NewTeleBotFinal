# PowerShell script to add stop_loss and take_profit to all Trade() instances
$content = Get-Content -Path "backend\tests\test_pr_051_etl_comprehensive.py" -Raw

# Add SL/TP before "volume=" in Trade() instances that don't have stop_loss
$pattern = '(?s)(Trade\([^)]*?)(\s+volume=)'
$replacement = '$1' + "`r`n            stop_loss=Decimal(`"1940.00`"),`r`n            take_profit=Decimal(`"1970.00`")," + '$2'

# First pass: add before volume if stop_loss not present  
$content = $content -replace $pattern, {
    param($match)
    if ($match.Value -match 'stop_loss') {
        $match.Value
    } else {
        $match.Groups[1].Value + "`r`n            stop_loss=Decimal(`"1940.00`"),`r`n            take_profit=Decimal(`"1970.00`")," + $match.Groups[2].Value
    }
}

Set-Content -Path "backend\tests\test_pr_051_etl_comprehensive.py" -Value $content -NoNewline
Write-Output "Fixed all Trade() instances"
