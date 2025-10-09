
@echo off
SETLOCAL ENABLEDELAYEDEXPANSION
git add -A
for /f "tokens=1-5 delims=/ " %%d in ("%date%") do set d=%%f-%%e-%%d
set msg=Auto push %d% %time%
git commit -m "%msg%"
git pull --rebase
git push
echo Done.
