# commands_selftest.py — Selftest command for Freelancer Bot
# Shows sample job from Freelancer + PeoplePerHour + Skywalker

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import logging
from platform_freelancer import get_items as get_freelancer_jobs
from platform_peopleperhour import get_items as get_pph_jobs
from platform_skywalker import fetch_skywalker_jobs

log = logging.getLogger("selftest")

async def selftest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        "🧪 Running self-test...\nFetching sample jobs from Freelancer, PeoplePerHour, and Skywalker..."
    )

    try:
        freelancer_jobs = get_freelancer_jobs(["logo"])
        pph_jobs = get_pph_jobs(["logo"])
        skywalker_jobs = await fetch_skywalker_jobs(["logo"])
    except Exception as e:
        log.error(f"Selftest error: {e}")
        await update.message.reply_text(f"❌ Selftest failed: {e}")
        return

    messages = []
    if freelancer_jobs:
        j = freelancer_jobs[0]
        msg = (
            "🌐 <b>Freelancer Sample</b>\n"
            f"🔹 <b>{j.get('title','Untitled')}</b>\n"
            f"💰 {j.get('budget_display', j.get('budget','N/A'))}\n"
            f"🔑 Keyword: <code>{j.get('matched_keyword','N/A')}</code>\n"
            f"🔗 <a href='{j.get('url')}'>View on Freelancer</a>"
        )
        messages.append(msg)

    if pph_jobs:
        j = pph_jobs[0]
        msg = (
            "🧩 <b>PeoplePerHour Sample</b>\n"
            f"🔹 <b>{j.get('title','Untitled')}</b>\n"
            f"💰 {j.get('budget_display', j.get('budget','N/A'))}\n"
            f"🔑 Keyword: <code>{j.get('matched_keyword','N/A')}</code>\n"
            f"🔗 <a href='{j.get('url')}'>View on PeoplePerHour</a>"
        )
        messages.append(msg)

    if skywalker_jobs:
        j = skywalker_jobs[0]
        msg = (
            "🇬🇷 <b>Skywalker Sample</b>\n"
            f"🔹 <b>{j.get('title','Untitled')}</b>\n"
            f"💰 {j.get('budget_display', j.get('budget','N/A'))}\n"
            f"🔑 Keyword: <code>{j.get('matched_keyword','N/A')}</code>\n"
            f"🔗 <a href='{j.get('url')}'>View on Skywalker</a>"
        )
        messages.append(msg)

    if not messages:
        await update.message.reply_text(
            "⚠️ No jobs found for Freelancer, PPH or Skywalker within the last 48h."
        )
        return

    await update.message.reply_text(
        "\n\n".join(messages),
        parse_mode="HTML",
        disable_web_page_preview=False,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("✅ OK", callback_data="selftest_ok")]]
        ),
    )

    log.info(f"Selftest executed by {user.id} ({user.username})")
