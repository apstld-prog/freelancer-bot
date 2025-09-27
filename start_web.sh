#!/usr/bin/env bash
set -euo pipefail

echo "[web] starting server..."
# unbuffered, prefixed logs
(stdbuf -oL -eL python server.py 2>&1 | awk '{print "[server] " $0; fflush() }')
