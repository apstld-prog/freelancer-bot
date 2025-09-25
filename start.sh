#!/usr/bin/env bash
set -e

echo "Starting health server..."
python server.py &

echo "Starting Telegram bot (polling, single instance)..."
python bot.py &

echo "Starting worker..."
python worker.py
