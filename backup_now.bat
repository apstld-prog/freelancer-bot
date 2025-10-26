@echo off
REM ======================================================
REM 🚀 FREELANCER BOT BACKUP SCRIPT (Full folders + files)
REM ======================================================

setlocal enabledelayedexpansion

REM === Ρυθμίσεις φακέλων ===
set PROJECT_DIR=%~dp0
set BACKUP_DIR=%PROJECT_DIR%backups
set BACKUP_NAME=backup_%date:~10,4%-%date:~4,2%-%date:~7,2%_%time:~0,2%-%time:~3,2%-%time:~6,2%.zip

REM === Αφαίρεση κενών από ώρα (π.χ. 09 -> 9) ===
set BACKUP_NAME=%BACKUP_NAME: =0%

REM === Δημιουργία φακέλου backup εάν δεν υπάρχει ===
if not exist "%BACKUP_DIR%" (
    mkdir "%BACKUP_DIR%"
)

echo =====================================================
echo 📦 Δημιουργία πλήρους backup του project:
echo Από: %PROJECT_DIR%
echo Προς: %BACKUP_DIR%\%BACKUP_NAME%
echo =====================================================

REM === Εξαιρέσεις (π.χ. venv, cache, __pycache__) ===
set EXCLUDES=-xr!venv -xr!__pycache__ -xr!.git -xr!backups

REM === Εκτέλεση backup (περιλαμβάνει φακέλους) ===
cd /d "%PROJECT_DIR%"
if exist "%BACKUP_DIR%\%BACKUP_NAME%" del "%BACKUP_DIR%\%BACKUP_NAME%"
powershell -Command "Compress-Archive -Path * -DestinationPath '%BACKUP_DIR%\%BACKUP_NAME%' -Force"

echo ✅ Backup ολοκληρώθηκε επιτυχώς!
echo 📁 Αποθηκεύτηκε ως: %BACKUP_DIR%\%BACKUP_NAME%

pause
