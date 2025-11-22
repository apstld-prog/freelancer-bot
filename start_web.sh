#!/usr/bin/env bash
set -e

echo "[web] starting server..."

# ΕΚΜΕΤΑΛΛΕΥΟΜΑΣΤΕ ΤΟ ΙΔΙΟ event loop
# ΔΕΝ κάνουμε ούτε build_application() ούτε application.run_* εδώ.
# ΜΟΝΟ uvicorn, που θα καλέσει το FastAPI lifespan μας.
exec uvicorn server:app --host 0.0.0.0 --port 10000
