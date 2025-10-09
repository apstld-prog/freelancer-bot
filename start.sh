#!/usr/bin/env bash
set -e
export PYTHONUNBUFFERED=1
python -u server.py &
python -u worker.py
