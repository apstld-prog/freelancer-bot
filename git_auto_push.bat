@echo off
:: Auto-commit & push to main. Keeps Render in sync.
:: -----------------------------------------------
:: Usage: double-click or run from repo root.

setlocal ENABLEDELAYEDEXPANSION

:: Fail on error
cmd /c exit /b 0

:: Compute timestamp (YYYY-MM-DD_HHMMSS)
for /f "tokens=1-4 delims=/ " %%a in ("%date%") do (
    set YY=%%d
    set MM=%%b
    set DD=%%c
)
for /f "tokens=1-3 delims=:. " %%h in ("%time%") do (
    set HH=%%h
    set MI=%%i
    set SS=%%j
)
if 1%!HH! LSS 110 set HH=0!HH!
set TS=%YY%-%MM%-%DD%_%HH%%MI%%SS%

:: Ensure we're in repo
git rev-parse --is-inside-work-tree >nul 2>&1 || (
  echo Not inside a Git repository. Aborting.
  exit /b 1
)

:: Show branch
for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD') do set BR=%%b
echo Current branch: %BR%

:: Stage all changes (incl. new/deleted)
git add -A

:: If nothing to commit, still push in case of remote changes
git diff --cached --quiet || (
  git commit -m "Auto push %TS%"
)

:: Rebase on latest main (safe for single-user)
git pull --rebase origin %BR%

:: Push branch
git push origin %BR%

:: OPTIONAL: update movable stable tag (uncomment if you want)
:: git tag -f stable
:: git push -f origin stable

echo Done. Pushed %BR% at %TS%.
endlocal
