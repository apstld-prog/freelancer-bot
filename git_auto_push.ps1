# ===============================
# Git auto commit + push script
# ===============================

# Πήγαινε στον φάκελο του script
Set-Location -Path $PSScriptRoot

Write-Host "🚀 Adding all changes..." -ForegroundColor Cyan
git add -A

# Δημιούργησε commit message με ημερομηνία και ώρα
$DATE = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$MSG = "Auto commit $DATE"

Write-Host "📝 Commit with message: $MSG" -ForegroundColor Yellow
git commit -m "$MSG"

Write-Host "⬆️ Pushing to origin main..." -ForegroundColor Green
git push origin main

Write-Host "✅ Done! Changes pushed successfully." -ForegroundColor Magenta
Pause
