#!/usr/bin/env bash
set -euo pipefail

echo "[start] launching services..."

# μικρό helper για prefix στα logs και επιστροφή PID
start_service() {
  local name="$1"; shift
  # stdbuf για unbuffered logs, awk για prefix
  (stdbuf -oL -eL "$@" 2>&1 | awk -v p="[$name] " '{ print p $0; fflush() }') &
  echo $!
}

# ξεκίνα services
server_pid=$(start_service server python server.py)
worker_pid=$(start_service worker python worker.py)
bot_pid=$(start_service bot    python bot.py)

echo "[start] pids -> server:$server_pid worker:$worker_pid bot:$bot_pid"

# καθαρός τερματισμός
term_all() {
  echo "[start] terminating children..."
  kill "$server_pid" "$worker_pid" "$bot_pid" 2>/dev/null || true
}
trap term_all SIGINT SIGTERM

# περίμενε όποιο τελειώσει πρώτο
wait -n || true

# αν ένα πέσει, τερμάτισε και τα υπόλοιπα για να μην μείνουν ορφανά
term_all
wait || true

echo "[start] all services stopped"
