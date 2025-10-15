# ==========================================
# 🚀 Force Git Auto Push Script (Render Safe)
# ==========================================
# Branch: main
# Λειτουργία: Κάνει force commit & push ακόμα κι αν δεν υπάρχουν αλλαγές.
# Χρήση: powershell -ExecutionPolicy Bypass -File .\git_auto_push.ps1
# ==========================================

# Σταμάτα σε λάθος
$ErrorActionPreference = "Stop"

Write-Host "====================================================="
Write-Host "🔁 Starting Force Git Auto Push to MAIN..."
Write-Host "====================================================="

# Πήγαινε στο path του script
Set-Location -Path (Split-Path -Parent $MyInvocation.MyCommand.Definition)

# Βεβαιώσου ότι υπάρχει git repo
if (-not (Test-Path ".git")) {
    Write-Host "❌ No Git repository found here."
    exit 1
}

# Προαιρετικά: τυπική καθαριότητα CRLF (για Windows)
Write-Host "🧹 Normalizing line endings..."
git config core.autocrlf true

# Ενημέρωσε remote origin
git fetch origin main

# Εμφάνισε status
$gitStatus = git status --short
if (-not $gitStatus) {
    Write-Host "ℹ️ No changes detected — forcing artificial update..."
    # Δημιούργησε dummy αρχείο για να ενεργοποιηθεί commit
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    "Force update $timestamp" | Out-File -Encoding utf8 "force_update.flag"
    git add force_update.flag
} else {
    Write-Host "✅ Changes detected, committing normally..."
}

# Δημιούργησε commit με timestamp
$commitMsg = "Force update $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
git add .
git commit -am $commitMsg

# Κάνε push στο main με force
Write-Host "🚀 Pushing to origin/main..."
git push origin main --force

Write-Host "====================================================="
Write-Host "✅ Repo pushed successfully to MAIN branch!"
Write-Host "====================================================="
