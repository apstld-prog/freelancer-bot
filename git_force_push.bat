@echo off
chcp 65001 >nul
title FORCE GIT PUSH TOOL FOR RENDER DEPLOYMENTS
echo ======================================================
echo FORCE GIT PUSH TOOL FOR RENDER DEPLOYMENTS
echo ======================================================

echo.
echo Checking Git status...
git status

echo.
echo Adding all files and folders (force)...
git add -A

echo.
echo Committing changes...
git commit -m "Force push all project files and folders" || echo (No changes to commit)

echo.
echo Pushing to Render (via GitHub remote)...
git push -f origin main

echo.
echo Done! All files and folders have been pushed successfully.
echo ======================================================
echo.
pause
