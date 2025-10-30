@echo off
title FREELANCER BOT - FULL SCHEMA REBUILD
echo ======================================================
echo 🚀 FREELANCER BOT — FULL SCHEMA REBUILD (Windows)
echo ======================================================

REM === 1️⃣ Load DATABASE_URL from environment ===
IF "%DATABASE_URL%"=="" (
    echo ❌ ERROR: DATABASE_URL is not set.
    echo ------------------------------------------------------
    echo Please set it manually before running this script.
    echo Example:
    echo    set DATABASE_URL=postgres://user:pass@host:5432/dbname
    echo ------------------------------------------------------
    pause
    exit /b
)

REM === 2️⃣ Confirm rebuild ===
echo This will completely DROP and REBUILD your Render database schema.
echo Press CTRL+C to cancel or any key to continue...
pause >nul

REM === 3️⃣ Drop and recreate schema ===
echo ------------------------------------------------------
echo 🧹 Dropping and recreating schema "public" ...
echo ------------------------------------------------------
psql "%DATABASE_URL%" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
IF ERRORLEVEL 1 (
    echo ❌ Failed to drop/create schema.
    pause
    exit /b
)

REM === 4️⃣ Apply rebuild_schema.sql ===
echo ------------------------------------------------------
echo 🛠️  Applying rebuild_schema.sql ...
echo ------------------------------------------------------
psql "%DATABASE_URL%" -f rebuild_schema.sql
IF ERRORLEVEL 1 (
    echo ❌ Schema rebuild failed.
    pause
    exit /b
)

REM === 5️⃣ Done! ===
echo ======================================================
echo ✅ Database schema rebuilt successfully!
echo ======================================================
echo.
echo 🔁 You can now redeploy or restart your Render service.
echo    (or run safe_restart.sh in Render Shell)
echo ======================================================
pause
