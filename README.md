\# Freelancer Alerts Bot (Affiliate Ready)



\## Features

\- Keyword-based job alerts (Upwork mock; plug your sources)

\- Country filter (US,UK,DE,...)

\- Inline actions: ⭐ Keep (save), 🙈 Dismiss (mute)

\- No duplicate alerts per user

\- Affiliate links support

\- Single Render service: health server + bot + worker



\## Setup (Local)

1\) python -m venv .venv \&\& source .venv/bin/activate

2\) pip install -r requirements.txt

3\) cp .env.example .env  # fill with your values

4\) python - <<'PY'

from db import Base, engine; Base.metadata.create\_all(engine)

print("DB initialized")

PY

5\) In one terminal: `python bot.py`

6\) In another: `python worker.py`



\## Deploy on Render (Single Web Service)

\- Runtime: Python

\- Start Command: `bash start.sh`

\- Health Check Path: `/healthz`

\- Environment:

&nbsp; - BOT\_TOKEN=...

&nbsp; - DB\_URL=REDACTED_DB_URL

&nbsp; - UPWORK\_AFFILIATE\_ID=...

&nbsp; - FREELANCER\_AFFILIATE\_ID=...

&nbsp; - FIVERR\_AFFILIATE\_ID=...

\- Build Command (optional): `pip install -r requirements.txt`



\## Notes

\- `worker.py` currently uses mocked jobs. Swap `fetch\_jobs()` with real integrations (API/scraping/RSS).

\- Use `/setcountry US,UK` to restrict alerts by country.

\- Use `/savejob <id>` or button ⭐ to keep; `/dismissjob <id>` or 🙈 to mute.





## Deploy on Render (single service)
1. Create a Web Service → Build command: `pip install -r requirements.txt` → Start command: `./start.sh`.

2. Set Environment Variables:
   - `BOT_TOKEN` (or `TELEGRAM_TOKEN`) — the bot token from @BotFather

   - `DATABASE_URL` — e.g. `postgresql+psycopg2://USER:PASSWORD@HOST:5432/DBNAME`

   - `WEBHOOK_SECRET` — e.g. `hook-secret-777`

   - `WEBHOOK_BASE_URL` — your Render URL, e.g. `https://your-service.onrender.com`

   - Optional: `TRIAL_DAYS`, `ADMIN_IDS`, `STATS_WINDOW_HOURS`, `AFFILIATE_PREFIX`

3. Ensure port is exposed via `start.sh` (Uvicorn listens on `$PORT`).

4. After deploy, check Logs for “Webhook set to …/webhook/SECRET” and “✅ Bot is ready”.

5. Test by sending `/start` to the bot.

