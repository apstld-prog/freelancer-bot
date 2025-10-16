@echo off
setlocal
set PS1=%~dp0git_force_push.ps1
powershell -NoExit -ExecutionPolicy Bypass -File "%PS1%" %*
endlocal
