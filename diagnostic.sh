#!/bin/bash
set -e

echo "======================================================"
echo "🔍 FREELANCER BOT EXTENDED DIAGNOSTIC TOOL"
echo "======================================================"
echo "📅 Date: $(date -u)"
echo

# STEP 1: ENVIRONMENT
echo "👉 STEP 1: Environment summary"
echo "------------------------------------------------------"
echo "Service: ${RENDER_SERVICE_NAME:-freelancer-bot-ns7s}"
python3 --version || echo "Python N/A"
echo

# STEP 2: WORKER PROCESSES
echo "👉 STEP 2: Worker processes"
echo "------------------------------------------------------"
ps aux | grep worker_ | grep -v grep || echo "⚠️ No worker processes found"
echo

# STEP 3: FEED EVENT STATS
echo "👉 STEP 3: Feed event stats (last 24h)"
echo "------------------------------------------------------"
python3 - <<'PYCODE'
from db_events import get_platform_stats
try:
    stats = get_platform_stats(24)
    if not stats:
        print("⚠️ No events in last 24h.")
    else:
        for k,v in stats.items():
            print(f"✅ {k}: {v} jobs recorded")
except Exception as e:
    print("❌ Feed stats failed:", e)
PYCODE
echo

# STEP 4: FRESHNESS CHECK
echo "👉 STEP 4: Recent events check (1h freshness)"
echo "------------------------------------------------------"
python3 - <<'PYCODE'
from db import get_session
from sqlalchemy import text
from datetime import datetime, timedelta, timezone
try:
    with get_session() as s:
        ts = datetime.now(timezone.utc) - timedelta(hours=1)
        rows = s.execute(text("SELECT source, COUNT(*) FROM feed_events WHERE ts >= :ts GROUP BY source"), {"ts": ts}).fetchall()
        if not rows:
            print("⚠️ No events in the last hour — workers might be idle.")
        else:
            for r in rows:
                print(f"✅ Recent activity: {r[0]} => {r[1]} entries")
except Exception as e:
    print("❌ Freshness check failed:", e)
PYCODE
echo

# STEP 5: SYSTEM SNAPSHOT
echo "👉 STEP 5: Memory & uptime snapshot"
echo "------------------------------------------------------"
uptime
free -h
echo

echo "✅ Extended diagnostic complete."
echo "======================================================"
