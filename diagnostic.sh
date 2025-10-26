echo ""
echo "👉 STEP 5: Check running Python processes (Render watchdog)"
echo "------------------------------------------------------"
ps -ef | grep python | grep -v grep

echo ""
echo "👉 STEP 6: Last exit codes of background workers"
echo "------------------------------------------------------"
jobs -l

echo ""
echo "👉 STEP 7: Render service uptime and memory usage"
echo "------------------------------------------------------"
uptime
free -m

echo ""
echo "👉 STEP 8: Render environment check (active Python files)"
echo "------------------------------------------------------"
find /opt/render/project/src -maxdepth 1 -type f -name "*.py" -printf "%f\n"

echo ""
echo "✅ Extended diagnostic complete."
echo "======================================================"
