@echo off
title GIT SUPER PUSH TOOL (NO BOM SAFE VERSION)
cd /d "%~dp0"

:menu
cls
echo ======================================================
echo                  GIT SUPER PUSH TOOL
echo             SAFE - UTF8 WITHOUT BOM ONLY
echo ======================================================
echo.
echo  Select mode:
echo.
echo    1) Normal Push
echo    2) Force Refresh Push
echo    3) Full Rewrite Push (UTF8 No BOM)
echo    4) Exit
echo.
set /p choice=Enter choice (1-4): 

if "%choice%"=="1" goto normal
if "%choice%"=="2" goto refresh
if "%choice%"=="3" goto rewrite
if "%choice%"=="4" exit
goto menu

:normal
cls
echo [NORMAL PUSH]
git add -A
git commit -m "Normal sync commit" || echo (No changes)
git push
pause
goto menu

:refresh
cls
echo [FORCE REFRESH]
echo %date% %time% > .force_git_sync
git add -A
git commit -m "Force refresh commit"
git push --force
pause
goto menu

:rewrite
cls
echo [FULL REWRITE - UTF8 WITHOUT BOM]

for /f "delims=" %%F in ('git ls-files') do (
    echo Rewriting %%F
    powershell -NoLogo -NoProfile -ExecutionPolicy Bypass ^
      "(Get-Content -Raw '%%F') | Set-Content -Encoding UTF8NoBOM '%%F'"
)

git add -A
git commit -m "Full rewrite (UTF8 without BOM)"
git push --force

pause
goto menu
