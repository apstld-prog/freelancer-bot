@echo off
title FORCE GIT PUSH TOOL FOR RENDER DEPLOYMENTS
echo ======================================================
echo FORCE GIT PUSH TOOL FOR RENDER DEPLOYMENTS
echo ======================================================
echo.

REM Step 1: Clean Git cache (force refresh all files)
echo Cleaning Git cache...
git rm -r --cached . >nul 2>&1
echo.

REM Step 2: Add ALL files and folders (including nested)
echo Adding all project files and folders...
git add -A
echo.

REM Step 3: Create a commit with timestamp (so Render redeploys)
for /f "tokens=1-3 delims=/ " %%a in ("%date%") do (
  set datestr=%%c-%%a-%%b
)
for /f "tokens=1-2 delims=: " %%a in ("%time%") do (
  set timestr=%%a-%%b
)
set commitmsg=Force full push %datestr%_%timestr%
echo Creating commit: %commitmsg%
git commit -m "%commitmsg%" || echo (No changes to commit)
echo.

REM Step 4: Push to Render remote
echo Pushing to Render (via GitHub remote)...
git push origin main --force
echo.

echo ======================================================
echo Done! All files (including bot.py) have been pushed.
echo ======================================================
pause
