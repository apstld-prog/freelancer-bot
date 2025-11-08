@echo off
echo ======================================================
echo   GIT FORCE FULL REFRESH - TOUCH ALL FILES
echo   (Forces Git to treat everything as modified)
echo ======================================================
echo.

:: Move to script directory (repo root)
cd /d %~dp0

echo [+] Forcing modification timestamps on ALL tracked files...

for /f "delims=" %%F in ('git ls-files') do (
    powershell -Command "(Get-Item '%%F').LastWriteTime = Get-Date"
)

echo.
echo [+] Staging ALL files...
git add -A

echo [+] Creating commit...
git commit -m "FORCE REFRESH - artificial file changes" || echo (Commit may be empty)

echo [+] Forcing push to remote...
git push --force

echo.
echo ✅ Force refresh + push completed successfully.
echo ======================================================
pause
