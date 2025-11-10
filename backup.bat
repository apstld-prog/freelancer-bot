@echo off
setlocal ENABLEDELAYEDEXPANSION

:: ======================================================
:: FIX: Force script to run from its own folder
:: ======================================================
cd /d "%~dp0"

title FREELANCER BOT BACKUP TOOL

echo ===============================================
echo            BACKUP TOOL (ADVANCED)
echo ===============================================
echo.
echo   1) Full backup
echo   2) Python only
echo   3) Configs only
echo.
set /p choice=Enter choice (1-3): 

if "%choice%"=="1" goto full
if "%choice%"=="2" goto pyonly
if "%choice%"=="3" goto configs

echo Invalid choice.
pause
exit

:: ------------------------------------------------------
:prepare
set PROJECT_DIR=%cd%
set BACKUP_DIR=%PROJECT_DIR%\backups

if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"

for /f "tokens=1-3 delims=/" %%a in ("%date%") do (
    set YY=%%c
    set MM=%%a
    set DD=%%b
)

set HH=%time:~0,2%
set HH=%HH: =0%
set NN=%time:~3,2%
set SS=%time:~6,2%

set TS=%YY%-%MM%-%DD%_%HH%-%NN%-%SS%

echo.
echo Timestamp: %TS%
echo Project directory: %PROJECT_DIR%
echo Backup directory : %BACKUP_DIR%
echo.

goto :eof

:: ------------------------------------------------------
:full
call :prepare
set ZIPFILE=%BACKUP_DIR%\backup_full_%TS%.zip

echo Creating FULL backup...
powershell -NoLogo -NoProfile -Command ^
    "Compress-Archive -Path '%PROJECT_DIR%\*' -DestinationPath '%ZIPFILE%' -CompressionLevel Optimal"

echo.
echo Backup created: %ZIPFILE%
pause
exit

:: ------------------------------------------------------
:pyonly
call :prepare
set ZIPFILE=%BACKUP_DIR%\backup_py_%TS%.zip

echo Creating PYTHON-ONLY backup...
powershell -NoLogo -NoProfile -Command ^
    "Compress-Archive -Path '%PROJECT_DIR%\*.py' -DestinationPath '%ZIPFILE%' -CompressionLevel Optimal"

echo.
echo Backup created: %ZIPFILE%
pause
exit

:: ------------------------------------------------------
:configs
call :prepare
set ZIPFILE=%BACKUP_DIR%\backup_configs_%TS%.zip

echo Creating CONFIGS backup...
powershell -NoLogo -NoProfile -Command ^
    "Compress-Archive -Path '%PROJECT_DIR%\*.sh','%PROJECT_DIR%\*.txt','%PROJECT_DIR%\*.md','%PROJECT_DIR%\*.json','%PROJECT_DIR%\*.yaml','%PROJECT_DIR%\*.yml','%PROJECT_DIR%\*.sql' -DestinationPath '%ZIPFILE%' -CompressionLevel Optimal"

echo.
echo Backup created: %ZIPFILE%
pause
exit

