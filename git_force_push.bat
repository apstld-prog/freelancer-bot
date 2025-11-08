@echo off
echo ======================================================
echo   GIT FORCE PUSH - FULL OVERRIDE
echo ======================================================
echo.

:: Ensure we are in the repository root
cd /d %~dp0

echo [+] Staging ALL files...
git add -A

echo [+] Creating commit...
git commit -m "FORCE PUSH - full overwrite" || echo (Commit may be empty)

echo [+] Forcing push to remote...
git push --force

echo.
echo ✅ Force push completed successfully.
echo ======================================================
pause
