#!/bin/bash
set -e

echo "======================================================"
echo "🔍 FREELANCER BOT ADVANCED DIAGNOSTIC TOOL"
echo "======================================================"
echo "📅 Date: $(date -u)"
echo

# STEP 1: ENVIRONMENT SUMMARY
echo "👉 STEP 1: Environment summary"
echo "------------------------------------------------------"
echo "Render Service: ${RENDER_SERVICE_NAME:-freelancer-bot-ns7s}"
echo "Python $(python3 --version 2>/dev/null || echo 'N/A')"
echo "$(node -v 2>/dev/null || echo 'Node N/A')"
echo "Worker intervals: FREELANCER=${FREELANCER_INTERVAL:-N/A}, PPH=${PPH_INTERVAL:-N/A}, GREEK=${GREEK_INTERVAL:-N/A}"
echo "Keyword filter mode: ${KEYWORD_FILTER_MODE:-off}"
echo

# STEP 2: CLEANUP ZOMBIE / DEFUNCT PROCESSES
echo "👉 STEP 2: Cleanup of zombie/defunct workers"
echo "------------------------------------------------------"
ZOMBIES=$(ps -eo stat,comm | grep 'Z' | grep python || true)
if [ -z "$ZOMBIES" ]; then
  echo "✅ No zombie processes found."
else
  echo "⚠️ Found zombie processes:"
  echo "$ZOMBIES"
  echo "🔧 Killing them..."
  pkill -9 -f worker_ || true
  pkill -9 -f uvicorn || true
  echo "✅ Cleanup done."
fi
echo

# STEP 3: ADMIN USER CHECK
echo "👉 STEP 3: Admin user consistency"
echo "------------------------------------------------------"
python3 - <<'PYCODE'
from db import get_session
from sqlalchemy import text

ADMIN_ID = 5254014824
try:
    with get_session() as s:
        conn = s.connection()
        # Αναζήτηση πίνακα
        table = conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema='public' AND table_name ILIKE 'user%';
        """)).fetchone()
        if not table:
            print("❌ No user table found in DB.")
            exit()
        table = table[0]
        print(f"✅ Found user table: {table}")

        # Έλεγχος ύπαρξης admin (ψάχνει σε id ή telegram_id)
        res = conn.execute(text(f"""
            SELECT id, telegram_id FROM "{table}"
            WHERE id=:id OR telegram_id=:id
        """), {"id": ADMIN_ID}).fetchone()

        if res:
            print(f"✅ Admin user exists: {res}")
        else:
            print("⚠️ Admin user not found. You can run: python3 init_users.py")
except Exception as e:
    print(f"❌ Admin check failed: {e}")
PYCODE
echo

# STEP 4: KEYWORDS CHECK
echo "👉 STEP 4: Keyword consistency check"
echo "------------------------------------------------------"
python3 - <<'PYCODE'
from db import get_session
from sqlalchemy import text

try:
    with get_session() as s:
        conn = s.connection()
        # Ελέγχει ύπαρξη keywords
        kwcount = conn.execute(text("SELECT COUNT(*) FROM keyword;")).scalar()
        if kwcount == 0:
            print("⚠️ No keywords found in DB.")
        else:
            print(f"✅ Found {kwcount} total keywords in DB.")
except Exception as e:
    print(f"❌ Keyword check failed: {e}")
PYCODE
echo

# STEP 5: PLATFORM FETCH TEST
echo "👉 STEP 5: Fetch test per platform"
echo "------------------------------------------------------"
python3 - <<'PYCODE'
from platform_freelancer import fetch_freelancer_jobs
from platform_peopleperhour import fetch_pph_jobs
from platform_skywalker import fetch_skywalker_jobs
import asyncio

async def main():
    try:
        f = await fetch_freelancer_jobs(["logo"])
        print(f"✅ Freelancer: {len(f)} jobs fetched")
    except Exception as e:
        print(f"⚠️ Freelancer fetch error: {e}")

    try:
        p = await fetch_pph_jobs(["logo"])
        print(f"✅ PeoplePerHour: {len(p)} jobs fetched")
    except Exception as e:
        print(f"⚠️ PeoplePerHour fetch error: {e}")

    try:
        s = await fetch_skywalker_jobs(["logo"])
        print(f"✅ Skywalker: {len(s)} jobs fetched")
    except Exception as e:
        print(f"⚠️ Skywalker fetch error: {e}")

asyncio.run(main())
PYCODE
echo

# STEP 6: MEMORY & SYSTEM SNAPSHOT
echo "👉 STEP 6: Memory, uptime and system load"
echo "------------------------------------------------------"
uptime
free -h
echo

echo "✅ Full diagnostic complete."
echo "======================================================"
