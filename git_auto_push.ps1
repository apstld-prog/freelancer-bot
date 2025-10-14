# ==========================================
# PowerShell Script: git_auto_push.ps1
# Purpose: Auto commit & push all project updates to Render (via GitHub)
# Version: Enhanced Display + Redeploy Fallback
# ==========================================

Write-Host "`n🔍 Checking repository status..." -ForegroundColor Cyan

# Stage all files
git add -A

# Check git status for changes
$status = git status --porcelain

if ($status) {
    # There are changes
    $fileCount = ($status | Measure-Object -Line).Lines
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $commitMessage = "Auto push ($fileCount file(s) changed) - $timestamp"

    Write-Host "📝 Committing $fileCount file(s)..." -ForegroundColor Yellow
    git commit -m "$commitMessage"

    Write-Host "🚀 Pushing changes to GitHub..." -ForegroundColor Cyan
    git push origin main

    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Push successful — Render will deploy shortly." -ForegroundColor Green
    } else {
        Write-Host "❌ Push failed. Please check your connection or credentials." -ForegroundColor Red
    }
}
else {
    # No detected changes
    Write-Host "⚠️ No changes found. Forcing redeploy..." -ForegroundColor Yellow
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Set-Content -Path ".force_redeploy" -Value "# redeploy $timestamp"
    git add .force_redeploy
    git commit -m "Force redeploy - $timestamp"
    git push origin main

    if ($LASTEXITCODE -eq 0) {
        Write-Host "🎯 Forced redeploy triggered successfully!" -ForegroundColor Green
    } else {
        Write-Host "❌ Push failed during redeploy trigger." -ForegroundColor Red
    }
}

Write-Host "`n🕓 Completed at $(Get-Date -Format 'HH:mm:ss')`n" -ForegroundColor Gray
