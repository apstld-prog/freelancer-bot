#!/bin/bash
set -e

echo "======================================================"
echo "🔍 FREELANCER BOT ADVANCED DIAGNOSTIC TOOL"
echo "======================================================"
echo "📅 Date: $(date -u)"
echo

echo "👉 STEP 1: Environment summary"
echo "------------------------------------------------------"
echo "Render Service: ${RENDER_SERVICE_NAME:-freelancer-bot}"
python3 --version 2>/dev/null
node --version 2>/dev/null || true
echo "Worker intervals: FREELANCER=${FREELANCER_INTERVAL}, PPH=${PPH_INTERVAL}, GREEK=${GREEK_INTERVAL}"
echo "Keyword filter mode: ${KEYWORD_FILTER_MODE}"
echo

echo "👉 STEP 2: Cleanup of zombie/defunct workers"
echo "------------------------------------------------------"
Z=$(ps aux | grep defunct | grep python || true)
if [ -n "$Z" ]; then
  echo "⚠️ Found zombie or defunct Python workers. Cleaning..."
  pkill -f worker_freelancer.py 2>/dev/null || true
  pkill -f worker_pph.py 2>/dev/null || true
  pkill -f worker_skywalker.py 2>/dev/null || true
  pkill -f uvicorn 2>/dev/null || true
  echo "✅ Cleanup complete."
else
  echo "✅ No zombie processes found."
fi
echo

echo "👉 STEP 3: Keyword consistency check"
echo "------------------------------------------------------"
python3 - <<'PYCODE'
import os, sys
sys.path.append(os.path.dirname(__file__))

session = None
try:
    from db import session
except ImportError:
    try:
        from db import SessionLocal
        session = SessionLocal()
    except ImportError:
        try:
            from db import get_session
            session = get_session()
        except Exception:
            session = None

if not session:
    print("❌ No valid DB session found in db.py (session, SessionLocal, or get_session missing).")
else:
    try:
        from db_keywords import Keyword
        defaults = ["logo","lighting","dialux","relux","led","φωτισμός","luminaire"]
        existing = [k.keyword for k in session.query(Keyword).all()]
        missing = [k for k in defaults if k not in existing]

        print(f"🗂 Found {len(existing)} keywords in DB.")
        if missing:
            print(f"⚠️ Missing: {missing}")
        else:
            print("✅ All default keywords present.")
    except Exception as e:
        print(f"⚠️ Could not verify keywords: {e}")
PYCODE
echo

echo "👉 STEP 4: Fetch test per platform"
echo "------------------------------------------------------"
python3 - <<'PYCODE'
import asyncio, sys, os
sys.path.append(os.path.dirname(__file__))

try:
    from platform_freelancer import fetch_freelancer_jobs
    from platform_peopleperhour import fetch_pph_jobs
    from platform_skywalker import fetch_skywalker_jobs
except Exception as e:
    print(f"⚠️ Import error in platform modules: {e}")
    exit(0)

async def run():
    try:
        f = await fetch_freelancer_jobs(["test"])
        print(f"✅ Freelancer: {len(f)} jobs fetched")
    except Exception as e:
        print(f"⚠️ Freelancer fetch error: {e}")
    try:
        p = await fetch_pph_jobs(["test"])
        print(f"✅ PeoplePerHour: {len(p)} jobs fetched")
    except Exception as e:
        print(f"⚠️ PeoplePerHour fetch error: {e}")
    try:
        s = await fetch_skywalker_jobs(["test"])
        print(f"✅ Skywalker: {len(s)} jobs fetched")
    except Exception as e:
        print(f"⚠️ Skywalker fetch error: {e}")

asyncio.run(run())
PYCODE
echo

echo "👉 STEP 5: Memory, uptime and system load"
echo "------------------------------------------------------"
uptime
free -h || true
echo

echo "✅ Full diagnostic complete."
echo "======================================================"
