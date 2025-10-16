@echo off
setlocal

rem ===== Header =====
echo.
echo ==========================================
echo   Git Auto Push - Simple & Stable
echo ==========================================
echo.

rem ===== Check tools =====
where git >NUL 2>&1
if errorlevel 1 (
  echo [ERROR] Git not found in PATH.
  goto END
)

where python >NUL 2>&1
if errorlevel 1 (
  echo [WARN] Python not found in PATH. Continuing without Python checks.
)

rem ===== (Optional) Python syntax check - DISABLED by default =====
rem if exist "bot.py" (
rem   python -c "import py_compile; py_compile.compile(r'bot.py', doraise=True)" 2>NUL
rem   if errorlevel 1 (
rem     echo [ERROR] Syntax error in bot.py
rem     goto END
rem   )
rem )
rem if exist "worker_runner.py" (
rem   python -c "import py_compile; py_compile.compile(r'worker_runner.py', doraise=True)" 2>NUL
rem   if errorlevel 1 (
rem     echo [ERROR] Syntax error in worker_runner.py
rem     goto END
rem   )
rem )

echo.
echo ==========================================
echo   GIT STAGE / COMMIT / PUSH
echo ==========================================
echo.

git add -A
if errorlevel 1 (
  echo [ERROR] git add failed.
  goto END
)

set "MSG=Deploy: auto push"
if not "%~1"=="" set "MSG=%*"

git commit -m "%MSG%"
if errorlevel 1 (
  echo [INFO] Nothing to commit (working tree clean).
)

git push
if errorlevel 1 (
  echo [ERROR] git push failed.
  goto END
)

echo.
echo ==========================================
echo   PUSH COMPLETED SUCCESSFULLY
echo ==========================================
echo.

:END
echo.
echo Press any key to close this window...
pause >NUL
endlocal
