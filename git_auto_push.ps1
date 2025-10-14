# ==========================================
# PowerShell Script: git_auto_push.ps1
# Purpose: Auto-commit & push all updates to Render (via GitHub)
# ==========================================

Write-Host "🔄 Checking for changes..." -ForegroundColor Cyan

# Stage all files
git add -A

# Try committing changes
$commitMessage = "Auto push update - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
$commitOutput = git commit -m "$commitMessage" 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Commit created: $commitMessage" -ForegroundColor Green
} else {
    if ($commitOutput -match "nothing to commit") {
        Write-Host "⚠️ No changes detected. Creating .force_redeploy to trigger Render build..." -ForegroundColor Yellow
        $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
        Set-Content -Path ".force_redeploy" -Value "# redeploy $timestamp"
        git add .force_redeploy
        git commit -m "Force rebuild trigger - $timestamp"
        Write-Host "✅ Forced redeploy commit created." -ForegroundColor Green
    } else {
        Write-Host "❌ Commit failed:`n$commitOutput" -ForegroundColor Red
        exit 1
    }
}

# Push changes
Write-Host "🚀 Pushing to GitHub..." -ForegroundColor Cyan
git push origin main

if ($LASTEXITCODE -eq 0) {
    Write-Host "🎉 Push successful! Render will auto-deploy shortly." -ForegroundColor Green
} else {
    Write-Host "❌ Push failed. Please check your connection or credentials." -ForegroundColor Red
}
