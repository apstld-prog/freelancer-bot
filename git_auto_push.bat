@echo off
setlocal enabledelayedexpansion
REM git_auto_push.bat — robust auto add/commit/pull --rebase/push

cd /d "%~dp0"

REM Sanity
git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Not a git repository.
  pause & exit /b 1
)

REM Branch: arg1 or current
set "BRANCH=%~1"
if "%BRANCH%"=="" for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD') do set "BRANCH=%%b"
if "%BRANCH%"=="" set "BRANCH=main"

REM Force flag as arg2
set "FORCEFLAG=%~2"

echo.
echo === Check for unfinished rebase ===
if exist ".git\rebase-merge" (
  echo [WARN] Detected unfinished rebase.
  if /I "%FORCEFLAG%"=="--continue-rebase" (
    echo Attempting: git add -A ^& git rebase --continue
    git add -A
    git rebase --continue
    if errorlevel 1 (
      echo [ERROR] rebase --continue failed. Resolve conflicts, then:
      echo   git add -A
      echo   git rebase --continue
      pause & exit /b 1
    )
  ) else if /I "%FORCEFLAG%"=="--abort-rebase" (
    echo Attempting: git rebase --abort
    git rebase --abort
    if errorlevel 1 (
      echo [ERROR] rebase --abort failed. You may need to remove .git\rebase-merge manually.
      echo   rmdir /S /Q .git\rebase-merge
      pause & exit /b 1
    )
  ) else (
    echo Use one of:
    echo   git_auto_push.bat %BRANCH% --continue-rebase
    echo   git_auto_push.bat %BRANCH% --abort-rebase
    pause & exit /b 1
  )
)

REM Safe timestamp (PowerShell) for message
for /f "usebackq delims=" %%t in (`powershell -NoProfile -Command "(Get-Date).ToString('yyyy-MM-dd HH:mm:ss')"`) do set "TS=%%t"
set "MSG=Auto commit %TS%"

echo.
echo === Refresh index ===
git update-index -q --refresh

echo.
echo === Add/Commit if needed ===
git add -A
git diff --quiet && git diff --cached --quiet
if errorlevel 1 (
  echo Commit message: %MSG%
  git commit -m "%MSG%" || git commit -m "Auto commit"
) else (
  echo No changes to commit.
)

echo.
echo === Fetch + pull --rebase --autostash origin/%BRANCH% ===
git fetch origin || (echo [ERROR] fetch failed. & pause & exit /b 1)
git pull --rebase --autostash origin %BRANCH%
if errorlevel 1 (
  echo [ERROR] Rebase failed. Resolve conflicts, then:
  echo   git status
  echo   git add -A
  echo   git rebase --continue
  pause & exit /b 1
)

echo.
echo === Push to origin/%BRANCH% ===
if /I "%FORCEFLAG%"=="--force" (
  echo Using --force-with-lease
  git push --force-with-lease origin %BRANCH%
) else (
  git push origin %BRANCH%
)

if errorlevel 1 (
  echo [WARN] Push failed. Try again or run manually:
  echo   git pull --rebase --autostash origin %BRANCH%
  echo   git push origin %BRANCH%
) else (
  echo ✅ Done! Changes pushed successfully.
)

echo.
pause
endlocal
