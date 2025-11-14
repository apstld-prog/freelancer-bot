#!/usr/bin/env bash
set -euo pipefail

echo "[worker] launching bot + worker..."

start_bg() {
  local name="$1"; shift
  (stdbuf -oL -eL "$@" 2>&1 | awk -v p="[$name] " '{ print p $0; fflush() }') &
  echo $!
}

worker_pid=$(start_bg worker python worker.py)
bot_pid=$(start_bg bot    python bot.py)

echo "[worker] pids -> worker:$worker_pid bot:$bot_pid"

cleanup() {
  echo "[worker] terminating children..."
  kill "$worker_pid" "$bot_pid" 2>/dev/null || true
}
trap cleanup SIGINT SIGTERM

# Αν πέσει ένα, ρίξε και το άλλο για καθαρό restart από το Render
wait -n || true
cleanup
wait || true
echo "[worker] stopped"
