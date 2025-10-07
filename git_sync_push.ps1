@echo off
setlocal enabledelayedexpansion
REM git_auto_push.bat — Auto add/commit/pull --rebase/push for origin main (robust)

REM 1) Go to repo root (this script's folder)
cd /d "%~dp0"

REM 2) Sanity checks
git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
  echo [ERROR] This folder is not a git repository.
  pause
  exit /b 1
)

REM Determine target branch (arg1 or current)
set "BRANCH=%~1"
if "%BRANCH%"=="" (
  for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD') do set "BRANCH=%%b"
)
if "%BRANCH%"=="" set "BRANCH=main"

REM Optional: --force flag as 2nd arg -> force-with-lease push
set "FORCEFLAG=%~2"

REM Safe timestamp via PowerShell
for /f "usebackq delims=" %%t in (`powershell -NoProfile -Command "(Get-Date).ToString('yyyy-MM-dd HH:mm:ss')"`) do set "TS=%%t"
set "MSG=Auto commit %TS%"

echo.
echo === Refresh index ===
git update-index -q --refresh

echo.
echo === Adding changes (if any) ===
git add -A

REM Check if there is anything to commit (working tree OR staged)
git diff --quiet && git diff --cached --quiet
if errorlevel 1 (
  echo Commit message: %MSG%
  git commit -m "%MSG%"
  if errorlevel 1 (
    echo [WARN] Commit failed. Trying fallback message...
    git commit -m "Auto commit"
  )
) else (
  echo No changes to commit.
)

echo.
echo === Fetch + pull --rebase --autostash from origin/%BRANCH% ===
git fetch origin
if errorlevel 1 (
  echo [ERROR] git fetch failed.
  pause
  exit /b 1
)

git pull --rebase --autostash origin %BRANCH%
if errorlevel 1 (
  echo.
  echo [ERROR] Rebase failed. Resolve conflicts, then run:
  echo   git status
  echo   git add -A
  echo   git rebase --continue
  echo and re-run this script.
  pause
  exit /b 1
)

echo.
echo === Pushing to origin/%BRANCH% ===
if /I "%FORCEFLAG%"=="--force" (
  echo Using --force-with-lease
  git push --force-with-lease origin %BRANCH%
) else (
  git push origin %BRANCH%
)

if errorlevel 1 (
  echo.
  echo [WARN] Push failed. Remote may have updated again.
  echo Try re-running the script, or use manually:
  echo   git fetch origin
  echo   git pull --rebase --autostash origin %BRANCH%
  echo   git push origin %BRANCH%
) else (
  echo.
  echo ✅ Done! Changes pushed successfully.
)

echo.
pause
endlocal
