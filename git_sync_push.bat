@echo off
setlocal
REM Launch PowerShell script with safe defaults
pwsh -ExecutionPolicy Bypass -File "%~dp0git_sync_push.ps1" %*
pause
