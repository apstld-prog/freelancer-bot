#!/bin/bash
set -e

echo "========================================"
echo "🚀 STARTING UNIFIED WORKER"
echo "========================================"
echo "Time: $(date)"
echo "Python: $(python3 --version)"
echo "----------------------------------------"

cd /opt/render/project/src

while true; do
  echo "[$(date)] Running unified worker once..."
  python3 worker_runner.py --debug || echo "Worker run failed, will retry."
  echo "[$(date)] Sleeping 60 seconds..."
  sleep 60
done