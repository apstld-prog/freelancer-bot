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



