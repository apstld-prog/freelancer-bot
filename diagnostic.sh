#!/bin/bash
echo "======================================================"
echo "🔍 FREELANCER BOT DIAGNOSTIC TOOL"
echo "======================================================"
echo "📅 Date: $(date)"
echo ""

echo "👉 STEP 1: Active processes"
echo "------------------------------------------------------"
ps aux | grep -E "worker_runner|server.py" | grep -v grep
echo ""

echo "👉 STEP 2: worker_runner.py (first 20 lines)"
echo "------------------------------------------------------"
head -n 20 worker_runner.py
echo ""

echo "👉 STEP 3: Running worker test..."
echo "------------------------------------------------------"
pkill -f worker_runner.py 2>/dev/null
python -u worker_runner.py &
sleep 6
echo ""

echo "👉 STEP 4: Last 40 log lines"
echo "------------------------------------------------------"
tail -n 40 logs || echo "(no logs found)"
echo ""

echo "✅ Diagnostic complete."
echo "======================================================"
