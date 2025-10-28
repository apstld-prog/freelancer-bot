#!/bin/bash
echo "======================================================"
echo "🔍 FREELANCER BOT EXTENDED DIAGNOSTIC TOOL (v2.2)"
echo "======================================================"
echo "📅 Date: $(date)"
echo

# STEP 1 — Environment
echo "👉 STEP 1: Environment summary"
echo "------------------------------------------------------"
echo "Service: freelancer-bot-ns7s"
python3 --version
echo

# STEP 2 — Workers
echo "👉 STEP 2: Worker processes"
echo "------------------------------------------------------"
ps aux | grep worker_ | grep -v grep || echo "⚠️ No worker processes found"
echo

# STEP 3 — Feed stats
echo "👉 STEP 3: Feed event stats (last 24h)"
echo "------------------------------------------------------"
psql "$DATABASE_URL" -c "
SELECT platform, COUNT(*) as jobs_last_24h
FROM job_event
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY platform;
" 2>/dev/null || echo "ℹ️ Skipped: DB not accessible"
echo

# STEP 4 — Recent events
echo "👉 STEP 4: Recent events check (1h freshness)"
echo "------------------------------------------------------"
psql "$DATABASE_URL" -c "
SELECT platform, COUNT(*) as recent_jobs
FROM job_event
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY platform;
" 2>/dev/null || echo "ℹ️ Skipped: DB not accessible"
echo

# STEP 5 — Memory snapshot
echo "👉 STEP 5: Memory & uptime snapshot"
echo "------------------------------------------------------"
uptime
free -h
echo

# STEP 6 — Keyword consistency
echo "👉 STEP 6: Keyword consistency per user"
echo "------------------------------------------------------"
python3 - <<'EOF'
import json, os
data_path = "data/keywords.json"
if os.path.exists(data_path):
    with open(data_path) as f:
        data = json.load(f)
    users = {}
    for k in data:
        users.setdefault(k["user_id"], []).append(k["keyword"])
    for uid, kws in users.items():
        print(f"👤 user_id={uid}: {len(kws)} keywords → {', '.join(kws)}")
else:
    print("⚠️ keywords.json not found")
EOF
echo

# STEP 7 — get_user_keywords()
echo "👉 STEP 7: get_user_keywords() verification"
echo "------------------------------------------------------"
python3 - <<'EOF'
try:
    from db_keywords import get_user_keywords
    print("✅ get_user_keywords():", get_user_keywords(5254014824))
except Exception as e:
    print("❌ get_user_keywords() failed:", e)
EOF
echo

# STEP 8 — Worker logs tail
echo "👉 STEP 8: Recent worker log tail"
echo "------------------------------------------------------"
for f in logs/worker_*.log; do
    echo "--- $f ---"
    tail -n 5 "$f"
    echo
done

echo "✅ Extended diagnostic complete."
echo "======================================================"
