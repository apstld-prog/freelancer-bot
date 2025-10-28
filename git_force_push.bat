@echo off
cd /d "%~dp0"

echo =====================================================
echo 🚀 GIT FORCE PUSH — FREELANCER BOT FULL PROJECT
echo =====================================================
echo.

REM Make sure git tracks all files including nested folders
git add -A

echo 🧩 Committing all local changes...
git commit -m "Auto push update (%date% %time%)" --allow-empty

echo 🔄 Forcing push to remote main branch...
git push -f origin main

echo ✅ Force push complete.
echo =====================================================
echo.

pause
