@echo off
REM --- git_auto_push.bat ---
REM Usage: double-click, or run from repo root.
REM Commits all changes and pushes to origin main (or current branch).

setlocal enabledelayedexpansion

REM Detect current branch
for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD') do set BRANCH=%%b

REM Add all changes
git add -A

REM Create timestamped commit message
for /f "tokens=1-5 delims=/:. " %%a in ("%date% %time%") do (
  set YYYY=%date:~6,4%
  set MM=%date:~3,2%
  set DD=%date:~0,2%
  set HH=%%d
  set MIN=%%e
)
set MSG=auto: %USERNAME% %YYYY%-%MM%-%DD% %HH%:%MIN%

git commit -m "%MSG%" 2>nul
IF %ERRORLEVEL% NEQ 0 (
  echo Nothing to commit.
)

echo Pushing to origin %BRANCH% ...
git push origin %BRANCH%

echo Done.
pause
