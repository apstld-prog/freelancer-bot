RESTORED BACKUP — 2025-10-11T05:34:45.186521Z

This archive matches your working setup and UI, with only *non-breaking* additions:
1) Updated `.env.example` to include all platform toggles, Skywalker feed URL, FX rates for USD conversion, and AFFILIATE_PREFIX placeholder.
2) Includes `run_git_auto_push.cmd` and `git_auto_push.bat` for one-click commit & push.

DEPLOY (Render, single service):
- Upload your .env with BOT_TOKEN, DATABASE_URL, WEBHOOK_BASE_URL, ADMIN_IDS, AFFILIATE_PREFIX.
- Make sure P_* toggles are set to 1 (enabled).
- Start command (unchanged): `bash start.sh`

ADMIN:
- `/users` — list users
- `/grant <telegram_id> <days>` — extend trial/license
- `/block` / `/unblock`
- `/broadcast <text>`
- `/feedsstatus` — last 24h per-platform counts

NOTES:
- Proposal/Original buttons are affiliate-safe: Original is the same wrapped link.
- Budget shows native currency plus USD (using FX_RATES).
