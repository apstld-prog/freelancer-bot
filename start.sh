#!/usr/bin/env bash
set -euo pipefail

echo "[start] launching web(server) + bot + worker..."

# Το Render ορίζει αυτόματα το $PORT. Βάζουμε default για local.
export PORT="${PORT:-10000}"
export PYTHONUNBUFFERED=1

# 1) Web server (ASGI) – ΠΡΕΠΕΙ να ακούει στο $PORT
#    Αν το app σου είναι "app" μέσα στο server.py (FastAPI/Starlette), αφήνεις όπως είναι:
python -m uvicorn server:app --host 0.0.0.0 --port "$PORT" --log-level info &
SERVER_PID=$!

# 2) Telegram bot (webhook mode – δεν χρειάζεται port)
python bot.py &
BOT_PID=$!

# 3) Worker (RSS/JSON fetch + notifications)
python worker.py &
WORKER_PID=$!

# Αν πέσει ένα, τερματίζουμε καθαρά
trap 'echo "[start] terminating children: $SERVER_PID $BOT_PID $WORKER_PID"; kill $SERVER_PID $BOT_PID $WORKER_PID 2>/dev/null || true' EXIT

# Περιμένουμε οποιοδήποτε process να τερματίσει και βγαίνουμε με το status του
wait -n $SERVER_PID $BOT_PID $WORKER_PID
exit $?
