@echo off
chcp 65001 >nul
echo =============================
echo   RUNNING FULL DIAGNOSTIC
echo =============================
python diagnostic_all.py > diagnostic_log.txt 2>&1
echo.
echo Diagnostic completed.
echo Log saved in diagnostic_log.txt
echo.
pause
