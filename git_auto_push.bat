@echo off
setlocal enabledelayedexpansion
REM git_auto_push.bat — Auto add/commit/pull --rebase/push for origin main

REM 1) Go to repo root (this script's folder)
cd /d "%~dp0"

REM 2) Sanity checks
git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
  echo [ERROR] This folder is not a git repository.
  pause
  exit /b 1
)

REM Optional: target branch (default main). You can call: git_auto_push.bat my-branch
set "BRANCH=%~1"
if "%BRANCH%"=="" set "BRANCH=main"

REM Optional: --force flag as 2nd arg -> force-with-lease push
set "FORCEFLAG=%~2"

echo.
echo === Adding all changes ===
git add -A

REM Commit only if there are staged changes
git diff --cached --quiet
if errorlevel 1 (
  for /f "tokens=1-3 delims=/ " %%a in ("%date%") do set TODAY=%%a-%%b-%%c
  set NOW=%time: =0%
  set MSG=Auto commit %TODAY% %NOW%
  echo Commit message: %MSG%
  git commit -m "%MSG%"
) else (
  echo No staged changes to commit.
)

echo.
echo === Fetch + pull --rebase from origin/%BRANCH% ===
git fetch origin
if errorlevel 1 (
  echo [ERROR] git fetch failed.
  pause
  exit /b 1
)

git pull --rebase origin %BRANCH%
if errorlevel 1 (
  echo.
  echo [ERROR] Rebase failed. Resolve conflicts, then run:
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
  echo Try re-running the script, or use:
  echo   git fetch origin
  echo   git pull --rebase origin %BRANCH%
  echo   git push origin %BRANCH%
  echo If you MUST overwrite remote history: add ^"--force^" as 2nd arg.
) else (
  echo.
  echo ✅ Done! Changes pushed successfully.
)

echo.
pause
endlocal
