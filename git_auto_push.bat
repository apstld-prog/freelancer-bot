@echo off
chcp 65001 >nul
cd /d "%~dp0"

:: ======== Auto Git Push =========
git add -A
git commit -m "auto update"
git push origin main
exit
