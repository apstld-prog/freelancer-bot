#!/usr/bin/env bash
set -Eeuo pipefail

echo "[start] launching services..."
PIDS=()

# Optional tiny web server for health checks (only if server.py exists)
if [[ -f "server.py" ]]; then
  python server.py &
  PIDS+=($!)
  echo "[start] server.py pid=${PIDS[-1]}"
fi

# Telegram bot (the ONLY polling process)
python bot.py &
PIDS+=($!)
echo "[start] bot.py pid=${PIDS[-1]}"

# Worker (no polling; uses Bot.send_message only)
python worker.py &
PIDS+=($!)
echo "[start] worker.py pid=${PIDS[-1]}"

term() {
  echo "[start] terminating children: ${PIDS[*]}"
  kill -TERM "${PIDS[@]}" 2>/dev/null || true
  wait
}
trap term SIGINT SIGTERM

set +e
wait -n
status=$?
echo "[start] a process exited with code $status — stopping others..."
term
exit $status
