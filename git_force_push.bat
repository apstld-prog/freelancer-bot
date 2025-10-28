@echo off
title 🔄 GIT FULL FORCE SYNC — DOUBLE CLICK VERSION
color 0A
cls
echo ======================================================
echo 🔄  GIT FORCE PUSH — FULL PROJECT SYNC (Double-Click)
echo ======================================================
echo.
echo This script will:
echo   1. Clean Git cache (untrack/retrack all files & folders)
echo   2. Add everything recursively
echo   3. Commit all changes
echo   4. Show detailed diff summary
echo   5. Force push to remote
echo ------------------------------------------------------
echo.
pause

REM Change directory to script location
cd /d "%~dp0"

echo ➤ Cleaning Git cache...
git rm -r --cached . >nul 2>&1
if %errorlevel% neq 0 (
    echo (nothing cached or already clean)
)
echo ✅ Cache cleaned.
echo.

echo ➤ Adding all project files and folders...
git add -A
echo ✅ Added all files recursively.
echo.

echo ➤ Committing all changes...
git commit -m "Force sync all project files" || echo (no changes to commit)
echo.

echo ➤ Showing what will be pushed (diff summary)...
git diff --stat HEAD~1 HEAD 2>nul || echo (no diff available)
echo.

echo ➤ Performing FORCE PUSH to remote repository...
git push -f
echo.

echo ======================================================
echo ✅ FULL FORCE SYNC COMPLETED SUCCESSFULLY
echo ======================================================
echo.
echo Close this window or press any key to exit.
pause >nul
exit
