#!/usr/bin/env bash
set -euo pipefail

export PYTHONUNBUFFERED=1
export PORT="${PORT:-10000}"

echo "==> launching web(server) + worker..."

# --- Web (Telegram webhook server)
python -u server.py & WEB_PID=$!

# --- Worker (fetches jobs from platforms + sends alerts)
python -u worker.py & WORKER_PID=$!

# Μείνε ζωντανός όσο ζει ένα από τα δύο και βγες αν πεθάνει κάποιο
wait -n "$WEB_PID" "$WORKER_PID"
EXIT_CODE=$?

# Αν πέσει κάτι, σκότωσε το άλλο για καθαρό restart από το Render
kill 0 || true
exit "$EXIT_CODE"
