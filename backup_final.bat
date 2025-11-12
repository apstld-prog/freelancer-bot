@echo off
chcp 65001 >nul
title FREELANCER-BOT BACKUP SYSTEM
echo ======================================
echo     FREELANCER-BOT BACKUP SYSTEM
echo ======================================
echo.

:: Ορισμός φακέλων
set "SRC=%~dp0"
set "DEST=%SRC%backups"
set "LOG=%SRC%backup_log.txt"

:: Δημιουργία φακέλου backups αν δεν υπάρχει
if not exist "%DEST%" mkdir "%DEST%"

:: Δημιουργία timestamp χωρίς ειδικούς χαρακτήρες
for /f "tokens=1-3 delims=/ " %%a in ("%date%") do set "DATE=%%a-%%b-%%c"
for /f "tokens=1-2 delims=:." %%a in ("%time%") do set "TIME=%%a-%%b"
set "FILENAME=backup_%DATE%_%TIME%.zip"

echo 🔄 Δημιουργία αντιγράφου ασφαλείας...
echo.

:: Εκτέλεση PowerShell σε νέο παράθυρο ώστε να ΜΗΝ κλείσει
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$src='%SRC%';" ^
  "$dest='%DEST%\%FILENAME%';" ^
  "$exclude=@('.git','__pycache__','.venv','backups');" ^
  "Write-Host '🗂️ Συλλογή αρχείων...';" ^
  "$files=Get-ChildItem -Path $src -Recurse -File | Where-Object { foreach($ex in $exclude){ if($_.FullName -like ('*'+$ex+'*')){return $false}};return $true };" ^
  "if($files.Count -eq 0){ Write-Host '⚠️ Δεν βρέθηκαν αρχεία για backup.' -ForegroundColor Yellow; } else { Write-Host ('📦 Δημιουργία ZIP: '+$dest); Compress-Archive -Path $files.FullName -DestinationPath $dest -CompressionLevel Optimal -Force; Write-Host ('✅ Backup ολοκληρώθηκε: '+$dest) -ForegroundColor Green; }" ^
  "Write-Host ''; Write-Host 'Πατήστε οποιοδήποτε πλήκτρο για έξοδο...'; Pause"

echo.
pause
