#!/bin/bash
set -e

echo "======================================================"
echo "ðŸ” FREELANCER BOT ADVANCED DIAGNOSTIC TOOL"
echo "======================================================"
echo "ðŸ“… Date: $(date -u)"
echo

echo "ðŸ‘‰ STEP 1: Environment summary"
echo "------------------------------------------------------"
echo "Render Service: ${RENDER_SERVICE_NAME:-freelancer-bot}"
python3 --version 2>/dev/null
node --version 2>/dev/null || true
echo "Worker intervals: FREELANCER=${FREELANCER_INTERVAL}, PPH=${PPH_INTERVAL}, GREEK=${GREEK_INTERVAL}"
echo "Keyword filter mode: ${KEYWORD_FILTER_MODE}"
echo

echo "ðŸ‘‰ STEP 2: Cleanup of zombie/defunct workers"
echo "------------------------------------------------------"
Z=$(ps aux | grep defunct | grep python || true)
if [ -n "$Z" ]; then
  echo "âš ï¸ Found zombie processes, killing..."
  pkill -f worker_freelancer.py 2>/dev/null || true
  pkill -f worker_pph.py 2>/dev/null || true
  pkill -f worker_skywalker.py 2>/dev/null || true
  pkill -f uvicorn 2>/dev/null || true
else
  echo "âœ… No zombie processes found."
fi
echo

echo "ðŸ‘‰ STEP 3: Keyword consistency check"
echo "------------------------------------------------------"
python3 - <<'PY'
import sys, os
sys.path.append(os.path.dirname(__file__))
from db import session
from db_keywords import Keyword

defaults = ["logo","lighting","dialux","relux","led","Ï†Ï‰Ï„Î¹ÏƒÎ¼ÏŒÏ‚","luminaire"]
existing = [k.keyword for k in session.query(Keyword).all()]
missing = [k for k in defaults if k not in existing]

print(f"ðŸ—‚ Found {len(existing)} keywords in DB.")
if missing:
    print(f"âš ï¸ Missing: {missing}")
else:
    print("âœ… All default keywords present.")
PY
echo

echo "ðŸ‘‰ STEP 4: Fetch test per platform"
echo "------------------------------------------------------"
python3 - <<'PY'
import asyncio, sys, os
sys.path.append(os.path.dirname(__file__))
from platform_freelancer import fetch_freelancer_jobs
from platform_peopleperhour import fetch_pph_jobs
from platform_skywalker import fetch_skywalker_jobs

async def run():
    try:
        f = await fetch_freelancer_jobs(["test"])
        p = await fetch_pph_jobs(["test"])
        s = await fetch_skywalker_jobs(["test"])
        print(f"âœ… Freelancer: {len(f)} jobs fetched")
        print(f"âœ… PeoplePerHour: {len(p)} jobs fetched")
        print(f"âœ… Skywalker: {len(s)} jobs fetched")
    except Exception as e:
        print(f"âš ï¸ Fetch error: {e}")
asyncio.run(run())
PY
echo

echo "ðŸ‘‰ STEP 5: Memory and uptime snapshot"
echo "------------------------------------------------------"
uptime
free -h
echo
echo "âœ… Full diagnostic complete."
echo "======================================================"


