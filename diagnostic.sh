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

try:
    from db_keywords import list_keywords, add_keywords
    from db import get_session
    session = get_session()
    defaults = ["logo","lighting","dialux","relux","led","φωτισμός","luminaire"]

    # Δοκιμή για admin (user_id = 5254014824)
    existing = []
    try:
        existing = list_keywords(5254014824)
    except Exception as e:
        print(f"⚠️ list_keywords() failed: {e}")

    if not existing:
        print("⚠️ No keywords found for admin. Seeding defaults...")
        try:
            added = add_keywords(5254014824, defaults)
            print(f"✅ Seeded {added} default keywords.")
        except Exception as e:
            print(f"❌ Could not seed defaults: {e}")
    else:
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
import asyncio, sys, os, inspect
sys.path.append(os.path.dirname(__file__))

try:
    from platform_freelancer import fetch_freelancer_jobs
    from platform_peopleperhour import fetch_pph_jobs
    from platform_skywalker import fetch_skywalker_jobs
except Exception as e:
    print(f"⚠️ Import error in platform modules: {e}")
    exit(0)

async def try_fetch(name, func):
    try:
        if inspect.iscoroutinefunction(func):
            result = await func(["test"])
        else:
            result = func(["test"])
        print(f"✅ {name}: {len(result)} jobs fetched")
    except Exception as e:
        print(f"⚠️ {name} fetch error: {e}")

async def main():
    await try_fetch("Freelancer", fetch_freelancer_jobs)
    await try_fetch("PeoplePerHour", fetch_pph_jobs)
    await try_fetch("Skywalker", fetch_skywalker_jobs)

asyncio.run(main())
PYCODE
echo

echo "👉 STEP 5: Memory, uptime and system load"
echo "------------------------------------------------------"
uptime
free -h || true
echo

echo "✅ Full diagnostic complete."
echo "======================================================"
