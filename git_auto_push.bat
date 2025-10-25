@echo off
echo ======================================================
echo 🚀 AUTO GIT PUSH TOOL FOR RENDER DEPLOYMENTS
echo ======================================================

cd /d "%~dp0"
echo.
echo 🔍 Checking Git status...

git add --all
echo.
echo 🧩 Committing changes...
git commit -m "Auto sync commit - full include (files + folders)" || echo (No changes to commit)

echo.
echo ☁️ Pushing to Render (via GitHub remote)...
git push

echo.
echo ✅ Done! All files and folders uploaded successfully.
echo ======================================================
echo.
pause
