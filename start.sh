#!/bin/bash
set -euo pipefail

echo "[start] launching services..."

# start server
python server.py &
server_pid=$!

# start worker
python worker.py &
worker_pid=$!

# start bot
python bot.py &
bot_pid=$!

# wait all
trap "echo '[start] terminating...'; kill $server_pid $worker_pid $bot_pid 2>/dev/null || true" SIGINT SIGTERM

wait -n

# if any exits, stop the others
kill $server_pid $worker_pid $bot_pid 2>/dev/null || true
