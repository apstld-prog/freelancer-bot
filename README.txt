Worker fixed — quick install
============================

Files included:
  - worker.py  (drop-in replacement)

Steps:
  1) Replace your existing /opt/render/project/src/worker.py with this one (or in your repo).
  2) Ensure your Start Command runs ./start.sh and that start.sh launches the worker with `nohup python -u worker.py > worker.log 2>&1 &`.
  3) Set WORKER_INTERVAL=60 (or what you prefer) in Render → Environment.
  4) Redeploy.

Verify:
  - tail -n 120 /opt/render/project/src/worker.log
    Expect:
      [Worker] ✅ Running (interval=60s)
      [deliver] users loaded: N
      [Worker] cycle completed — keywords=..., items=...

Notes:
  - Sends each job once globally (table sent_job) and prunes entries older than 7 days.
  - Filters jobs by your keywords (table keyword.value) and discards items older than 7 days if a date is present.
  - Uses BOT_TOKEN / TELEGRAM_BOT_TOKEN / TELEGRAM_TOKEN to send via Telegram Bot API.
