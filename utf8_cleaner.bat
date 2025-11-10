@echo off
title UTF-8 NO BOM CLEANER (Double-Click Version)
cd /d "%~dp0"

echo ===============================================
echo      UTF8 CLEANER - RUNNING PYTHON SCRIPT
echo ===============================================
echo.

REM ---- Check if Python exists ----
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Install Python 3.x and try again.
    echo.
    pause
    exit /b
)

REM ---- Check if script exists ----
if not exist utf8_cleaner.py (
    echo [ERROR] File utf8_cleaner.py not found in this folder.
    echo Put this BAT file in the SAME folder as utf8_cleaner.py
    echo.
    pause
    exit /b
)

echo Running Python cleaner...
echo.

python utf8_cleaner.py

echo.
echo ===============================================
echo Cleaning completed.
echo Output saved in utf8_report.txt
echo ===============================================

echo.
pause
