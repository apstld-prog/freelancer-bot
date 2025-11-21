#!/bin/bash
set -e

echo "========================================"
echo "🚀 STARTING UNIFIED WORKER"
echo "========================================"
echo "Time: $(date)"
echo "Python: $(python3 --version)"
echo "----------------------------------------"

cd /opt/render/project/src

# Run the unified worker runner
exec python3 worker_runner.py
