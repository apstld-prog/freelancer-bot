@echo off
REM Always open a console and keep it open after running the script
cd /d "%~dp0"
start "" cmd /k git_auto_push.bat
