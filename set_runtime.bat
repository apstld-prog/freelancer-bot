@echo off
REM === set_runtime.bat ===
REM This script creates runtime.txt with Python 3.11.9,
REM commits it and pushes to GitHub.

echo python-3.11.9 > runtime.txt

git add runtime.txt
git commit -m "Pin Python 3.11.9 for Render"
git push

echo.
echo ===========================================
echo runtime.txt created and pushed successfully!
echo Remember to Clear build cache & Deploy on Render.
echo ===========================================
pause
