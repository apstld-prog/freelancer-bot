
import asyncio, logging, traceback
from db import get_session
from db_jobs import insert_job_if_new, mark_job_sent
from db_users import get_active_users

import platform_freelancer as pf
import platform_peopleperhour as pph
import platform_skywalker as psw
import platform_careerjet as pcj
import platform_kariera as pk

log = logging.getLogger("worker")
logging.basicConfig(level=logging.INFO)

async def main():
    log.info("Fetching sources...")
    total = {}
    out = []
    try:
        r = pf.fetch_freelancer()
        out += r
        total["freelancer"] = len(r)
    except Exception as e:
        log.warning("Freelancer fetch error: %s", e)
    try:
        r = pph.fetch_peopleperhour()
        out += r
        total["peopleperhour"] = len(r)
    except Exception as e:
        log.warning("PeoplePerHour fetch error: %s", e)
    try:
        r = psw.fetch_skywalker()
        out += r
        total["skywalker"] = len(r)
    except Exception as e:
        log.warning("Skywalker fetch error: %s", e)
    try:
        r = pk.fetch_kariera()
        out += r
        total["kariera"] = len(r)
    except Exception as e:
        log.warning("Kariera fetch error: %s", e)
    try:
        r = pcj.fetch_careerjet()
        out += r
        total["careerjet"] = len(r)
    except Exception as e:
        log.warning("Careerjet fetch error: %s", e)

    log.info("Fetched summary: %s", total)

    if not out:
        log.info("No jobs fetched; exiting cycle.")
        return

    from telegram import Bot
    from config import BOT_TOKEN, KEYWORD_FILTER_MODE
    bot = Bot(token=BOT_TOKEN)

    with get_session() as s:
        users = get_active_users(s)
        log.info("Active users: %d", len(users))
        for user in users:
            try:
                # Keyword filter toggle
                if str(getattr(__import__('config'), 'KEYWORD_FILTER_MODE', 'off')).lower() == 'on':
                    kws = [k.lower() for k in user.keywords]
                    matched = [j for j in out if any(k in (j.title.lower() + ' ' + j.description.lower()) for k in kws)]
                else:
                    matched = out

                if not matched:
                    continue

                for j in matched:
                    if not insert_job_if_new(s, j):
                        continue
                    text_msg = (
                        f"<b>{getattr(j, 'title', '(no title)')}</b>\n"
                        f"  <b>Source:</b> {getattr(j, 'source', '-')}" 
                    )
                    url = getattr(j, 'url', None) or '#'
                    # simple body: keep style consistent; preview off
                    try:
                        await bot.send_message(chat_id=user.telegram_id, text=text_msg + f"\n<a href='{url}'>Open</a>",
                                               parse_mode='HTML', disable_web_page_preview=True)
                        mark_job_sent(s, j, user.id)
                    except Exception as e:
                        log.warning("Send failed to %s: %s", user.telegram_id, e)
            except Exception as e:
                log.warning("Worker loop user %s error: %s", user.id, e)
                traceback.print_exc()
        s.commit()

if __name__ == "__main__":
    asyncio.run(main())
