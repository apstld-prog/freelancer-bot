#!/bin/bash
# ======================================================
# 🔍 FREELANCER BOT EXTENDED DIAGNOSTIC TOOL (v3.0)
# ======================================================

echo "======================================================"
echo "🔍 FREELANCER BOT EXTENDED DIAGNOSTIC TOOL (v3.0)"
echo "======================================================"
echo "📅 Date: $(date -u)"
echo

# STEP 1 — Environment summary
echo "👉 STEP 1: Environment summary"
echo "------------------------------------------------------"
SERVICE_NAME=${RENDER_SERVICE_NAME:-"freelancer-bot"}
echo "Service: ${SERVICE_NAME}"
python3 --version
echo

# STEP 2 — Worker processes
echo "👉 STEP 2: Worker processes"
echo "------------------------------------------------------"
ps aux | grep "python3 -u workers/" | grep -v grep || echo "⚠️ No worker processes found"
echo

# STEP 3 — Feed event stats (last 24h and total)
echo "👉 STEP 3: Feed event stats (last 24h + total)"
echo "------------------------------------------------------"
psql "$DATABASE_URL" <<'SQL'
\pset format aligned
\pset border 2
\pset linestyle unicode
\pset title '📊 Jobs fetched per platform (last 24h)'
SELECT platform, COUNT(*) AS jobs_last_24h
FROM job_event
WHERE created_at >= NOW() - INTERVAL '24 hours'
GROUP BY platform
ORDER BY jobs_last_24h DESC;

\pset title '📈 Total jobs stored per platform'
SELECT platform, COUNT(*) AS total_jobs
FROM job_event
GROUP BY platform
ORDER BY total_jobs DESC;
SQL
echo

# STEP 4 — Recent events check (freshness within 1h)
echo "👉 STEP 4: Recent events check (1h freshness)"
echo "------------------------------------------------------"
psql "$DATABASE_URL" -c "
SELECT platform, COUNT(*) AS recent_jobs
FROM job_event
WHERE created_at >= NOW() - INTERVAL '1 hour'
GROUP BY platform;
"
echo

# STEP 5 — Memory & uptime snapshot
echo "👉 STEP 5: Memory & uptime snapshot"
echo "------------------------------------------------------"
uptime
free -h
echo

# STEP 6 — Keyword consistency per user
echo "👉 STEP 6: Keyword consistency per user"
echo "------------------------------------------------------"
psql "$DATABASE_URL" -c "
SELECT user_id, COUNT(*) AS kw_count, STRING_AGG(keyword, ', ' ORDER BY keyword) AS keywords
FROM user_keywords
GROUP BY user_id;
"
echo

# STEP 7 — get_user_keywords() verification
echo "👉 STEP 7: get_user_keywords() verification"
echo "------------------------------------------------------"
python3 - <<'PYCODE'
try:
    from db_keywords import get_user_keywords
    print("✅ get_user_keywords() import OK")
except Exception as e:
    print(f"❌ get_user_keywords() failed: {e}")
PYCODE
echo

# STEP 8 — Recent worker log tail
echo "👉 STEP 8: Recent worker log tail"
echo "------------------------------------------------------"
for f in logs/worker_freelancer.log logs/worker_pph.log logs/worker_skywalker.log; do
  if [ -f "$f" ]; then
    echo "--- $f ---"
    tail -n 15 "$f"
    echo
  else
    echo "⚠️ Missing: $f"
  fi
done

echo "✅ Extended diagnostic complete."
echo "======================================================"
