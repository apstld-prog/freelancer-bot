@echo off
title BACKUP TOOL (UTF8 NO BOM SAFE)
cd /d "%~dp0"

set "BACKUP_DIR=backups"
if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"

echo ===============================================
echo              BACKUP TOOL (SAFE)
echo ===============================================
echo.
echo 1) Full Backup
echo 2) Python Only
echo 3) Config Only
echo.
set /p choice=Enter choice (1-3): 

set timestamp=%DATE%_%TIME%
set timestamp=%timestamp::=-%
set timestamp=%timestamp:/=-%
set timestamp=%timestamp: =_%
set timestamp=%timestamp:.=-%

set "ZIP=%BACKUP_DIR%\backup_%choice%_%timestamp%.zip"

if "%choice%"=="1" goto full
if "%choice%"=="2" goto pythononly
if "%choice%"=="3" goto configonly

echo Invalid choice
pause
exit

:full
echo Creating FULL backup...
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass ^
  "Compress-Archive -Path * -DestinationPath '%ZIP%' -Force"
goto done

:pythononly
echo Creating PYTHON ONLY backup...
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass ^
  "Compress-Archive -Path *.py, workers\*.py -DestinationPath '%ZIP%' -Force"
goto done

:configonly
echo Creating CONFIG ONLY backup...
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass ^
  "Compress-Archive -Path *.txt, *.md, *.env, *.json, *.yml, *.yaml, *.cfg, *.ini, *.toml -DestinationPath '%ZIP%' -Force"
goto done

:done
echo.
echo Backup created: %ZIP%
echo ===============================================
pause
