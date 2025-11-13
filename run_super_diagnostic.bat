
@echo off
chcp 65001 >nul
echo ============================================
echo      SUPER DIAGNOSTIC — DUAL MODE
echo ============================================
echo [1] Running MODE 1 (Windows)
python diagnostic_mode1.py
echo.
echo [2] Running MODE 2 (Render SSH mode - requires running inside Render shell)
python diagnostic_mode2.py
echo --------------------------------------------
pause
