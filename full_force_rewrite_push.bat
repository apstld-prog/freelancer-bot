@echo off
echo ======================================================
echo   FULL FORCE REWRITE + GIT PUSH
echo   (Rewrites all files so Git sees new content)
echo ======================================================

setlocal ENABLEDELAYEDEXPANSION

echo.
echo [+] Rewriting all tracked files...

for /f "delims=" %%F in ('git ls-files') do (
    echo     - rewriting %%F
    powershell -NoLogo -NoProfile -ExecutionPolicy Bypass ^
      "(Get-Content -Raw '%%F') | Set-Content -Encoding UTF8 '%%F'"
)

echo.
echo [+] Staging all files...
git add -A

echo [+] Creating commit...
git commit -m "FULL FORCE REWRITE - all files rewritten"

echo [+] Force pushing to remote...
git push --force

echo.
echo âœ… DONE: All files rewritten and force pushed.
echo ======================================================
pause

