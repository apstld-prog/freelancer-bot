@echo off
echo ==========================================
echo   GIT SUPER PUSH - DOUBLE CLICK ENGINE
echo ==========================================
echo.

REM Move to the script folder
cd /d "%~dp0"

echo [1] Adding all changes...
git add -A

echo [2] Creating commit...
git commit -m "Auto push by double-click"

echo [3] Pulling latest with rebase...
git pull --rebase

echo [4] Pushing to Render...
git push

echo ------------------------------------------
echo DONE! Files successfully pushed.
echo Close this window.
pause
