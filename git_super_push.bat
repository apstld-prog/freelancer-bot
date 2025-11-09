@echo off
title GIT SUPER PUSH TOOL

:menu
cls
echo ======================================================
echo              GIT SUPER PUSH TOOL
echo ======================================================
echo.
echo  Select mode:
echo.
echo    1) Normal Push
echo    2) Force Refresh Push  (always creates commit)
echo    3) Full Rewrite Push   (rewrites every file)
echo    4) Exit
echo.
set /p choice=Enter choice (1-4): 

if "%choice%"=="1" goto normal
if "%choice%"=="2" goto force_refresh
if "%choice%"=="3" goto full_rewrite
if "%choice%"=="4" exit
goto menu

:normal
cls
echo [NORMAL PUSH]
echo Staging changes...
git add -A

echo Committing...
git commit -m "Normal sync commit" || echo (No changes to commit)

echo Pushing...
git push
pause
goto menu

:force_refresh
cls
echo [FORCE REFRESH PUSH]
echo Creating .force_git_sync...
echo %date% %time% > .force_git_sync

echo Staging...
git add -A

echo Committing forced commit...
git commit -m "Force refresh commit"

echo Pushing...
git push --force
pause
goto menu

:full_rewrite
cls
echo [FULL REWRITE PUSH]
echo Rewriting every tracked file...

for /f "delims=" %%F in ('git ls-files') do (
    echo Rewriting %%F
    powershell -NoLogo -NoProfile -ExecutionPolicy Bypass ^
      "(Get-Content -Raw '%%F') | Set-Content -Encoding UTF8 '%%F'"
)

echo Staging...
git add -A

echo Committing full rewrite...
git commit -m "FULL FORCE REWRITE - all files"

echo Force pushing...
git push --force
pause
goto menu






