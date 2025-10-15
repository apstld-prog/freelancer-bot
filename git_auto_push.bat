@echo off
:: ==========================================
:: 🚀 Force Git Auto Push Script (Render Safe)
:: ==========================================
:: Branch: main
:: Κάνει force commit & push ακόμα κι αν δεν υπάρχουν αλλαγές
:: ==========================================

echo =====================================================
echo 🔁 Starting Force Git Auto Push to MAIN...
echo =====================================================

:: Έλεγχος αν υπάρχει Git repo
if not exist ".git" (
    echo ❌ No Git repository found here.
    pause
    exit /b
)

:: Κανονικοποίηση CRLF (προαιρετικά)
git config core.autocrlf true

:: Fetch remote
git fetch origin main

:: Έλεγχος για αλλαγές
for /f "delims=" %%A in ('git status --short') do set CHANGES=%%A
if "%CHANGES%"=="" (
    echo ℹ️ No changes detected — forcing artificial update...
    set timestamp=%date%_%time%
    echo Force update %timestamp% > force_update.flag
    git add force_update.flag
) else (
    echo ✅ Changes detected, committing normally...
)

:: Δημιουργία commit με timestamp
for /f "tokens=1-3 delims=/- " %%a in ("%date%") do (
    set datestamp=%%c-%%b-%%a
)
for /f "tokens=1-2 delims=: " %%a in ("%time%") do (
    set timestamp=%%a%%b
)
set commitmsg=Force update %datestamp% %timestamp%
git add .
git commit -am "%commitmsg%"

:: Push στο main (force)
echo 🚀 Pushing to origin/main...
git push origin main --force

echo =====================================================
echo ✅ Repo pushed successfully to MAIN branch!
echo =====================================================
pause
