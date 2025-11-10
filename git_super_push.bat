@echo off
set PATH=%PATH%;C:\Program Files\Git\bin

echo.
echo ===============================
echo   GIT AUTO PUSH (SUPER MODE)
echo ===============================
echo.

:: ΠΗΓΑΙΝΕ ΣΤΟΝ ΦΑΚΕΛΟ ΤΟΥ SCRIPT
cd /d "%~dp0"

:: ΕΛΕΓΧΟΣ ΑΝ ΥΠΑΡΧΕΙ .git
if not exist ".git" (
    echo [ERROR] Δεν βρέθηκε φάκελος .git στο:
    echo %~dp0
    pause
    exit /b
)

:: AUTO ADD ALL
git add -A

:: AUTO COMMIT ΜΕ TIMESTAMP
set NOW=%DATE%_%TIME%
set NOW=%NOW::=-%
set NOW=%NOW:/=-%
set NOW=%NOW: =_%
git commit -m "AUTO-PUSH %NOW%"

:: AUTO PUSH
git push -f

echo.
echo ✅ ΤΕΛΟΣ — Ο ΚΩΔΙΚΑΣ ΕΞΕΠΕΜΦΘΗ ΣΤΟ GITHUB
echo.
pause
