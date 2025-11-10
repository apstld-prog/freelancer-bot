@echo off
setlocal enabledelayedexpansion

echo ======================================
echo     FREELANCER-BOT BACKUP SYSTEM
echo ======================================

:: Πήγαινε στον φάκελο όπου βρίσκεται το script
cd /d "%~dp0"

:: Δημιουργία ονόματος ZIP με timestamp
set DATESTAMP=%DATE%_%TIME%
set DATESTAMP=%DATESTAMP::=-%
set DATESTAMP=%DATESTAMP:/=-%
set DATESTAMP=%DATESTAMP: =_%
set DATESTAMP=%DATESTAMP:.=-%

set ZIPNAME=backup_%DATESTAMP%.zip

echo.
echo Δημιουργία backup: %ZIPNAME%
echo.

:: Αν υπάρχει παλιό zip με το ίδιο όνομα, σβήστο
if exist "%ZIPNAME%" del "%ZIPNAME%"

:: Δημιουργία ZIP χωρίς τον φάκελο .git
powershell -command "Compress-Archive -Path * -DestinationPath '%ZIPNAME%' -CompressionLevel Optimal -Exclude '.git','git_super_push.bat','backup.bat'"

echo.
echo ✅ Το backup ολοκληρώθηκε:
echo %ZIPNAME%
echo.
pause
