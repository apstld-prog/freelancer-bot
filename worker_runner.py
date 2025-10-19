import os
import time
import logging
import asyncio
from datetime import datetime, timedelta

from bot import build_application  # χρησιμοποιούμε τον ίδιο bot client
import platform_freelancer
import platform_peopleperhour

# ============ ΡΥΘΜΙΣΕΙΣ ============
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "5254014824"))
WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL", "120"))          # δευτ. default 2'
LOOKBACK_HOURS = int(os.getenv("LOOKBACK_HOURS", "48"))
MAX_SEND_PER_CYCLE = int(os.getenv("MAX_SEND_PER_CYCLE", "30"))     # όριο μηνυμάτων/κύκλο
# ===================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# Θυμόμαστε τι έχουμε ήδη στείλει για να αποφύγουμε διπλά
_SENT_IDS: set[str] = set()
_SENT_IDS_MAX = 5000


def _short(text: str, n: int = 320) -> str:
    if not text:
        return ""
    t = text.strip().replace("\r", " ").replace("\n", " ")
    return (t[:n] + "…") if len(t) > n else t


def _fmt_budget(job: dict) -> str:
    cur = (job.get("currency") or "").strip()
    bmin = job.get("budget_min") or job.get("budget")
    bmax = job.get("budget_max")
    if bmin and bmax:
        return f"{bmin}–{bmax} {cur}".strip()
    if bmin:
        return f"{bmin} {cur}".strip()
    return "?"


def _job_identity(job: dict) -> str:
    # Προτιμάμε ρητό ID, αλλιώς URL, αλλιώς τίτλο+currency+budget
    return (
        str(job.get("id"))
        or str(job.get("url"))
        or f"{job.get('title')}|{job.get('currency')}|{job.get('budget_min')}|{job.get('budget_max')}"
    )


async def _send_card(bot, chat_id: int, job: dict, source: str):
    title = job.get("title") or "(no title)"
    desc = _short(job.get("description") or "")
    budget = _fmt_budget(job)
    keyword = job.get("keyword") or ""
    url = job.get("url") or "#"

    # Κείμενο με το παλιό «style» (τίτλος/ budget / source / match / περιγραφή)
    msg = (
        f"📣 <b>{source.upper()}</b>\n\n"
        f"🔷 <b>{title}</b>\n"
        f"{desc}\n\n"
        f"💰 <b>Budget:</b> {budget}\n"
        f"🔎 <b>Keyword:</b> {keyword}\n\n"
        f"<a href=\"{url}\">View job</a>"
    )

    await bot.send_message(
        chat_id=chat_id,
        text=msg,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


async def _send_jobs(application, jobs: list[dict], source: str):
    bot = application.bot
    sent = 0
    for job in jobs:
        if sent >= MAX_SEND_PER_CYCLE:
            break
        jid = _job_identity(job)
        if not jid or jid in _SENT_IDS:
            continue
        try:
            await _send_card(bot, ADMIN_CHAT_ID, job, source)
            _SENT_IDS.add(jid)
            sent += 1
            if len(_SENT_IDS) > _SENT_IDS_MAX:
                # κρατάμε το set σε λογικό μέγεθος
                for _ in range(len(_SENT_IDS) - _SENT_IDS_MAX):
                    _SENT_IDS.pop()
            await asyncio.sleep(0.6)  # ευγενικό throttle προς Telegram
        except Exception as e:
            logging.error(f"[SEND_FAIL] {source}: {e}")
    if sent:
        logging.info(f"[{source.upper()}] ✅ sent {sent} jobs")
    else:
        logging.info(f"[{source.upper()}] nothing to send (after de-dup / limit)")


async def worker_loop():
    logging.info("[Worker] Starting (card-style formatting, internal send)…")
    app = build_application()
    async with app:
        await app.initialize()

        fresh_since = datetime.utcnow() - timedelta(hours=LOOKBACK_HOURS)

        while True:
            try:
                # ---- FREELANCER ----
                logging.debug("Fetching from Freelancer…")
                try:
                    freelancer_jobs = platform_freelancer.fetch(
                        fresh_since=fresh_since
                    )
                except TypeError:
                    # συμβατότητα παλιών signatures
                    freelancer_jobs = platform_freelancer.fetch()
                logging.info(f"[Freelancer] fetched={len(freelancer_jobs) if freelancer_jobs else 0}")
                if freelancer_jobs:
                    await _send_jobs(app, freelancer_jobs, "freelancer")

                # ---- PEOPLEPERHOUR ----
                logging.debug("Fetching from PeoplePerHour…")
                try:
                    pph_jobs = platform_peopleperhour.get_items(
                        fresh_since=fresh_since
                    )
                except TypeError:
                    pph_jobs = platform_peopleperhour.get_items()
                logging.info(f"[PeoplePerHour] fetched={len(pph_jobs) if pph_jobs else 0}")
                if pph_jobs:
                    await _send_jobs(app, pph_jobs, "peopleperhour")

                logging.info("[Worker] Cycle complete. Sleeping…")
                await asyncio.sleep(WORKER_INTERVAL)

            except Exception as e:
                logging.error(f"[Worker] loop error: {e}")
                await asyncio.sleep(WORKER_INTERVAL)


def main():
    asyncio.run(worker_loop())


if __name__ == "__main__":
    main()
