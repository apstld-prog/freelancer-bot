#!/bin/bash
echo "======================================================"
echo "🔍 FREELANCER BOT EXTENDED DIAGNOSTIC TOOL (v3.1)"
echo "======================================================"
echo "📅 Date: $(date -u)"

echo ""
echo "👉 STEP 1: Environment summary"
echo "------------------------------------------------------"
echo "Service: freelancer-bot-ns7s"
python3 --version

echo ""
echo "👉 STEP 2: Worker processes"
echo "------------------------------------------------------"
ps aux | grep worker_ | grep -v grep

echo ""
echo "👉 STEP 3: Feed event stats (last 24h + total)"
echo "------------------------------------------------------"
echo "📊 Jobs fetched per platform (last 24h)"
psql "$DATABASE_URL" -c "
SELECT platform, COUNT(*) AS jobs_last_24h
FROM job_event
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY platform;
"
echo ""
echo "📈 Total jobs stored per platform"
psql "$DATABASE_URL" -c "
SELECT platform, COUNT(*) AS total_jobs
FROM job_event
GROUP BY platform;
"

echo ""
echo "👉 STEP 4: Recent events check (1h freshness)"
echo "------------------------------------------------------"
psql "$DATABASE_URL" -c "
SELECT platform, COUNT(*) AS recent_jobs
FROM job_event
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY platform;
"

echo ""
echo "👉 STEP 5: Memory & uptime snapshot"
echo "------------------------------------------------------"
uptime
free -h

echo ""
echo "👉 STEP 6: Keyword consistency per user"
echo "------------------------------------------------------"
psql "$DATABASE_URL" -c "
SELECT u.id AS user_id, COUNT(k.keyword) AS keyword_count
FROM users u
LEFT JOIN user_keywords k ON k.user_id = u.id
GROUP BY u.id;
"

echo ""
echo "👉 STEP 7: get_user_keywords() verification"
echo "------------------------------------------------------"
python3 - <<'PYCODE'
from db_keywords import get_user_keywords
print("Sample test (user_id=1):", get_user_keywords(1))
PYCODE

echo ""
echo "👉 STEP 8: Recent worker log tail"
echo "------------------------------------------------------"
for log in logs/worker_*.log; do
  echo "--- $log ---"
  tail -n 10 "$log"
  echo ""
done

echo "✅ Extended diagnostic complete."
echo "======================================================"
