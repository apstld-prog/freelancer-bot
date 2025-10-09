@echo off
setlocal ENABLEDELAYEDEXPANSION

:: --------------------------------------------
:: Freelancer Alert Bot - One-click Backup
:: Φτιάχνει ZIP με timestamp & ΟΛΑ τα αρχεία
:: (περιλαμβάνει .git, εξαιρεί .venv, __pycache__, backups)
:: --------------------------------------------

:: 1) Timestamp YYYYMMDD-HHMMSS (ανεκτικό σε τοπικές ρυθμίσεις)
for /f "tokens=1-3 delims=/- " %%a in ("%date%") do (
  set D1=%%a& set D2=%%b& set D3=%%c
)
:: Προσπαθούμε να ανιχνεύσουμε ποιο είναι το έτος
if !D1! gtr 31 ( set YY=!D1!& set MM=!D2!& set DD=!D3! ) else (
  if !D3! gtr 31 ( set YY=!D3!& set MM=!D1!& set DD=!D2! ) else (
    set YY=!D2!& set MM=!D1!& set DD=!D3!
  )
)
for /f "tokens=1-3 delims=:.," %%h in ("%time%") do ( set HH=%%h& set MI=%%i& set SS=%%j )
if 1!HH! LSS 110 set HH=0!HH!
set TS=%YY%%MM%%DD%-%HH%%MI%%SS%

:: 2) Paths
set SRC=%CD%
set BACKUP_DIR=%SRC%\backups
set STAGE=%TEMP%\fab_stage_%RANDOM%
set ZIP_NAME=freelancer-bot_%TS%.zip
set ZIP_PATH=%BACKUP_DIR%\%ZIP_NAME%

:: 3) Ensure backup dir
if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"

:: 4) Δημιουργία staging αντιγράφου (χωρίς .venv, __pycache__, backups)
echo [+] Staging files...
robocopy "%SRC%" "%STAGE%" /MIR ^
/XD ".venv" "__pycache__" "backups" ".pytest_cache" ".mypy_cache" ".idea" ".vscode" ^
/XF "*.pyc" "*.pyo" "*.log" >nul

if errorlevel 8 (
  echo [!] ROBOCOPY returned error. Aborting.
  exit /b 1
)

:: 5) Manifest με πληροφορίες Git & ώρα backup
echo Project backup created at %date% %time%> "%STAGE%\BACKUP_MANIFEST.txt"
git rev-parse --is-inside-work-tree >nul 2>&1
if %errorlevel%==0 (
  for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD') do set GIT_BRANCH=%%b
  for /f "delims=" %%c in ('git rev-parse HEAD') do set GIT_COMMIT=%%c
  echo Git branch: %GIT_BRANCH%>> "%STAGE%\BACKUP_MANIFEST.txt"
  echo Git commit: %GIT_COMMIT%>> "%STAGE%\BACKUP_MANIFEST.txt"
  echo Untracked/modified files at time of backup:>> "%STAGE%\BACKUP_MANIFEST.txt"
  git status --porcelain >> "%STAGE%\BACKUP_MANIFEST.txt"
) else (
  echo (No git repository detected)>> "%STAGE%\BACKUP_MANIFEST.txt"
)

:: 6) Συμπίεση σε ZIP (PowerShell Compress-Archive)
echo [+] Creating ZIP: %ZIP_PATH%
powershell -NoProfile -Command "Compress-Archive -Path '%STAGE%\*' -DestinationPath '%ZIP_PATH%' -Force" || (
  echo [!] Compress-Archive failed. Aborting.
  rmdir /s /q "%STAGE%"
  exit /b 1
)

:: 7) Καθαρισμός staging
rmdir /s /q "%STAGE%"

echo [✓] Backup ready: %ZIP_PATH%
echo Πατήστε οποιοδήποτε πλήκτρο για έξοδο...
pause >nul
endlocal
