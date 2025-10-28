#!/bin/bash
set -e

echo "======================================================"
echo "🔍 FREELANCER BOT EXTENDED DIAGNOSTIC TOOL (v2.1)"
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
        rows = s.execute(
            text("SELECT source, COUNT(*) FROM feed_events WHERE ts >= :ts GROUP BY source"),
            {"ts": ts}
        ).fetchall()
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

# STEP 6: KEYWORD CONSISTENCY CHECK (DB LEVEL)
echo "👉 STEP 6: Keyword consistency per user"
echo "------------------------------------------------------"
python3 - <<'PYCODE'
from db import get_session
from sqlalchemy import text
try:
    with get_session() as s:
        # Detect which table exists: user or users
        tables = [r[0] for r in s.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public';")).fetchall()]
        table = "users" if "users" in tables else "user"
        print(f"🔎 Using table: {table}")

        users = s.execute(text(f"SELECT id, telegram_id, is_admin FROM {table} ORDER BY id")).fetchall()
        if not users:
            print("⚠️ No users found in table.")
        for uid, tid, admin in users:
            kw_count = s.execute(text("SELECT COUNT(*) FROM keyword WHERE user_id=:u"), {"u": uid}).scalar()
            print(f"👤 User ID={uid}, TG={tid}, admin={admin}, keywords={kw_count}")
            if admin:
                kws = s.execute(text("SELECT keyword FROM keyword WHERE user_id=:u ORDER BY keyword"), {"u": uid}).fetchall()
                if kws:
                    print("   ➜ Admin keywords:", ", ".join([k[0] for k in kws]))
                else:
                    print("   ⚠️ No keywords found for admin.")
except Exception as e:
    print("❌ Keyword check failed:", e)
PYCODE
echo

# STEP 7: FUNCTIONAL CHECK (get_user_keywords)
echo "👉 STEP 7: get_user_keywords() verification"
echo "------------------------------------------------------"
python3 - <<'PYCODE'
try:
    from db import get_user_keywords
    res = None
    try:
        import asyncio
        res = asyncio.run(get_user_keywords())
    except Exception:
        res = get_user_keywords()
    if not res:
        print("⚠️ get_user_keywords() returned nothing or empty.")
    else:
        print("✅ get_user_keywords() returned:")
        for uid, kws in res.items():
            print(f"   - user_id {uid}: {kws}")
except Exception as e:
    print("❌ get_user_keywords() failed:", e)
PYCODE
echo

echo "✅ Extended diagnostic complete."
echo "======================================================"
