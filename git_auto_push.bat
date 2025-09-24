@echo off
REM ===============================
REM Git auto commit + push script
REM ===============================

cd /d %~dp0

echo Adding all changes...
git add -A

REM Get current date and time for commit message
for /f "tokens=1-4 delims=/ " %%i in ("%date%") do set DATE=%%i-%%j-%%k
for /f "tokens=1-2 delims=: " %%i in ("%time%") do set TIME=%%i-%%j
set MSG=Auto commit %DATE% %TIME%

echo Committing with message: %MSG%
git commit -m "%MSG%"

echo Pushing to origin main...
git push origin main

echo.
echo ✅ Done! Changes pushed successfully.
pause
