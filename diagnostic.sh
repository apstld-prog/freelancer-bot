#!/bin/bash
set -e

echo "======================================================"
echo "🔍 FREELANCER BOT EXTENDED DIAGNOSTIC TOOL (v2.2)"
echo "======================================================"
echo "📅 Date: $(date -u)"
echo

# STEP 1–7 (όπως πριν)
bash diagnostic.sh --skip-step8 2>/dev/null || true

# STEP 8: Job statistics per keyword
echo "👉 STEP 8: Job statistics per keyword (last 24h)"
echo "------------------------------------------------------"
python3 - <<'PYCODE'
from db import get_session
from sqlalchemy import text
from datetime import datetime, timedelta, timezone
try:
    with get_session() as s:
        ts = datetime.now(timezone.utc) - timedelta(hours=24)
        rows = s.execute(text("""
            SELECT k.value, COUNT(e.id)
            FROM keyword k
            LEFT JOIN feed_events e ON e.keyword = k.value AND e.ts >= :ts
            GROUP BY k.value
            ORDER BY COUNT(e.id) DESC
        """), {"ts": ts}).fetchall()
        if not rows:
            print("⚠️ No recent job entries linked to keywords.")
        else:
            for kw, cnt in rows:
                print(f"🔹 {kw:<20} → {cnt} jobs (24h)")
except Exception as e:
    print("❌ Keyword job stats failed:", e)
PYCODE
echo

echo "✅ Extended diagnostic complete (v2.2)."
echo "======================================================"
