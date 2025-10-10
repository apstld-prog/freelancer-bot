
@echo off
setlocal ENABLEDELAYEDEXPANSION
REM --- Ensure we're inside a Git repo
git rev-parse --is-inside-work-tree >NUL 2>&1
if errorlevel 1 (
  echo [ERROR] This folder is not a Git repository.
  exit /b 1
)

REM --- Determine branch and remote
for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD') do set BRANCH=%%b
for /f "delims=" %%r in ('git remote') do set REMOTE=%%r
if "%REMOTE%"=="" set REMOTE=origin

echo.
echo [INFO] Branch: %BRANCH%
echo [INFO] Remote: %REMOTE%
git remote -v

REM --- Stage and commit all changes
git add -A
for /f "tokens=1-5 delims=/ " %%d in ("%date%") do set DATESTR=%%f-%%e-%%d
set MSG=Auto push %DATESTR% %time%
git commit -m "%MSG%" 1>NUL 2>&1
if errorlevel 1 (
  echo [INFO] Nothing to commit. Proceeding to push...
)

REM --- Pull --rebase to avoid conflicts
echo [INFO] Pulling latest from %REMOTE%/%BRANCH% ...
git pull --rebase %REMOTE% %BRANCH%
if errorlevel 1 (
  echo [ERROR] git pull --rebase failed. Resolve conflicts and retry.
  exit /b 1
)

REM --- Push
echo [INFO] Pushing to %REMOTE%/%BRANCH% ...
git push -u %REMOTE% %BRANCH%
if errorlevel 1 (
  echo [ERROR] git push failed. Check your remote/credentials.
  exit /b 1
)

REM --- Optional: trigger Render Deploy Hook if file exists
if exist .render_deploy_hook (
  set /p RENDER_HOOK=<.render_deploy_hook
  if not "%RENDER_HOOK%"=="" (
    echo [INFO] Triggering Render Deploy Hook...
    powershell -NoProfile -Command "try { Invoke-WebRequest -Method POST -Uri '%RENDER_HOOK%' ^| Out-Null; exit 0 } catch { exit 1 }"
    if errorlevel 1 (
      echo [WARN] Deploy hook call failed. Check the hook URL.
    ) else (
      echo [INFO] Deploy hook triggered successfully.
    )
  )
) else (
  echo [INFO] No .render_deploy_hook file found. Skipping manual deploy trigger.
  echo [HINT] To force a deploy even without code changes, create a file named .render_deploy_hook in repo root with your Render Deploy Hook URL.
)

echo [DONE] All set.
exit /b 0
