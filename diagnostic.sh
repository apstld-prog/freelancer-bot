#!/usr/bin/env bash
set -e

echo "======================================================"
echo "🔍 FREELANCER BOT ADVANCED DIAGNOSTIC TOOL"
echo "======================================================"
echo "📅 Date: $(date)"
echo

# STEP 1
echo "👉 STEP 1: Environment summary"
echo "------------------------------------------------------"
echo "Render Service: ${RENDER_SERVICE_NAME:-N/A}"
echo "Python: $(python3 --version 2>/dev/null || echo 'N/A')"
echo "Node: $(node -v 2>/dev/null || echo 'N/A')"
echo
echo "Worker intervals:"
echo "  FREELANCER_INTERVAL=${FREELANCER_INTERVAL:-N/A}"
echo "  PPH_INTERVAL=${PPH_INTERVAL:-N/A}"
echo "  GREEK_INTERVAL=${GREEK_INTERVAL:-N/A}"
echo
echo "Keyword filter mode: ${KEYWORD_FILTER_MODE:-off}"
echo "Webhook: ${WEBHOOK_URL:-N/A}"
echo

# STEP 2
echo "👉 STEP 2: Active processes"
echo "------------------------------------------------------"
ps -ef | grep -E "python|uvicorn" | grep -v grep || echo "(no Python processes running)"
echo

# STEP 3
echo "👉 STEP 3: Worker health check"
echo "------------------------------------------------------"
for f in workers/worker_freelancer.py workers/worker_pph.py workers/worker_skywalker.py; do
  if [ -f "$f" ]; then
    echo "✅ Found: $f"
  else
    echo "❌ Missing: $f"
  fi
done
echo

# STEP 4
echo "👉 STEP 4: Directory structure check"
echo "------------------------------------------------------"
for d in logs data workers; do
  if [ -d "$d" ]; then
    echo "✅ Folder exists: $d"
  else
    echo "❌ Missing folder: $d"
  fi
done
echo

# STEP 5
echo "👉 STEP 5: Quick fetch test (top 3 jobs per platform)"
echo "------------------------------------------------------"
python3 - <<'PYCODE'
import asyncio, json
from platform_freelancer import fetch_freelancer_jobs
from platform_peopleperhour import fetch_pph_jobs
from platform_skywalker import fetch_skywalker_jobs

async def main():
    try:
        f = await fetch_freelancer_jobs()
        p = await fetch_pph_jobs()
        s = await fetch_skywalker_jobs()
        print(f"Freelancer jobs: {len(f)}")
        print(f"PeoplePerHour jobs: {len(p)}")
        print(f"Skywalker jobs: {len(s)}\n")
        print("Sample Freelancer job:")
        print(json.dumps(f[:2], indent=2) if f else "No data")
        print("\nSample PPH job:")
        print(json.dumps(p[:2], indent=2) if p else "No data")
        print("\nSample Skywalker job:")
        print(json.dumps(s[:2], indent=2) if s else "No data")
    except Exception as e:
        print(f"⚠️ Error during fetch test: {e}")

asyncio.run(main())
PYCODE
echo

# STEP 6
echo "👉 STEP 6: Logs summary (last 10 lines each)"
echo "------------------------------------------------------"
for f in logs/worker_freelancer.log logs/worker_pph.log logs/worker_skywalker.log; do
  if [ -f "$f" ]; then
    echo "📄 $f"
    tail -n 10 "$f" || true
    echo
  else
    echo "⚠️ Log not found: $f"
  fi
done
echo

# STEP 7
echo "👉 STEP 7: Check for defunct or zombie processes"
echo "------------------------------------------------------"
ps aux | grep defunct | grep python || echo "✅ No defunct Python processes"
echo

# STEP 8
echo "👉 STEP 8: Memory and uptime snapshot"
echo "------------------------------------------------------"
uptime
free -h | awk 'NR==1; NR==2 {print $0}'
echo

echo "✅ Full diagnostic complete."
echo "======================================================"
