@echo off
setlocal ENABLEDELAYEDEXPANSION
for /f "tokens=1-4 delims=/ " %%a in ("%date%") do (
  set dd=%%a& set mm=%%b& set yyyy=%%c
)
for /f "tokens=1-2 delims=:." %%h in ("%time%") do (
  set hh=%%h& set nn=%%i
)
set TS=%yyyy%-%mm%-%dd%_%hh%%nn%
git add -A
git commit -m "auto: %TS%"
git push
echo Done.
