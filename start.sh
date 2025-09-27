#!/usr/bin/env bash
set -euo pipefail

echo "[start] launching web(server) + worker..."

start_bg() {
  local name="$1"; shift
  (stdbuf -oL -eL "$@" 2>&1 | awk -v p="[$name] " '{ print p $0; fflush() }') &
  echo $!
}

server_pid=$(start_bg server python server.py)
worker_pid=$(start_bg worker python worker.py)

trap "kill $server_pid $worker_pid 2>/dev/null || true" SIGINT SIGTERM
wait -n || true
kill $server_pid $worker_pid 2>/dev/null || true
wait || true
