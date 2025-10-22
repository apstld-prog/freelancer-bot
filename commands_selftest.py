# commands_selftest.py — Show sample jobs from Freelancer, PeoplePerHour, Skywalker
# Layout identical to production message style (Budget, Source, Match, Description, Buttons)

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from platform_freelancer import get_items as get_freelancer_jobs
from platform_peopleperhour import get_items as get_pph_jobs
from platform_skywalker import fetch_skywalker_jobs
import logging, datetime

log = logging.getLogger("selftest")

async def selftest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text("🧪 Running self-test...\nFetching sample jobs from all platforms...")

    try:
        freelancer_jobs = get_freelancer_jobs(["logo"]) or []
    except Exception as e:
        log.warning(f"Freelancer fetch failed: {e}")
        freelancer_jobs = []

    try:
        pph_jobs = get_pph_jobs(["logo"]) or []
    except Exception as e:
        log.warning(f"PPH fetch failed: {e}")
        pph_jobs = []

    try:
        skywalker_jobs = await fetch_skywalker_jobs(["logo"]) or []
    except Exception as e:
        log.warning(f"Skywalker fetch failed: {e}")
        skywalker_jobs = []

    messages = []

    # ---------- FREELANCER ----------
    if freelancer_jobs:
        j = freelancer_jobs[0]
        msg = (
            f"<b>{j.get('title','Untitled')}</b>\n"
            f"<b>Budget:</b> {j.get('budget_display','N/A')}\n"
            f"<b>Source:</b> Freelancer\n"
            f"<b>Match:</b> {j.get('matched_keyword','N/A')}\n"
            f"📋 {j.get('description','No description')}\n"
            f"{j.get('posted_ago','')}"
        )
        buttons = [
            [
                InlineKeyboardButton("📄 Proposal", url=j.get("proposal_url", j.get("original_url")) or j.get("url")),
                InlineKeyboardButton("🔗 Original", url=j.get("original_url") or j.get("url")),
            ],
            [
                InlineKeyboardButton("⭐ Save", callback_data=f"job:save:{j.get('id','0')}"),
                InlineKeyboardButton("🗑 Delete", callback_data="job:delete"),
            ],
        ]
        messages.append((msg, buttons))

    # ---------- PEOPLEPERHOUR ----------
    if pph_jobs:
        j = pph_jobs[0]
        msg = (
            f"<b>{j.get('title','Untitled')}</b>\n"
            f"<b>Budget:</b> {j.get('budget_display','N/A')}\n"
            f"<b>Source:</b> PeoplePerHour\n"
            f"<b>Match:</b> {j.get('matched_keyword','N/A')}\n"
            f"📋 {j.get('description','No description')}\n"
            f"{j.get('posted_ago','')}"
        )
        buttons = [
            [
                InlineKeyboardButton("📄 Proposal", url=j.get("proposal_url", j.get("original_url")) or j.get("url")),
                InlineKeyboardButton("🔗 Original", url=j.get("original_url") or j.get("url")),
            ],
            [
                InlineKeyboardButton("⭐ Save", callback_data=f"job:save:{j.get('id','0')}"),
                InlineKeyboardButton("🗑 Delete", callback_data="job:delete"),
            ],
        ]
        messages.append((msg, buttons))

    # ---------- SKYWALKER ----------
    if skywalker_jobs:
        j = skywalker_jobs[0]
        msg = (
            f"<b>{j.get('title','Untitled')}</b>\n"
            f"<b>Budget:</b> {j.get('budget_display','N/A')}\n"
            f"<b>Source:</b> Skywalker\n"
            f"<b>Match:</b> {j.get('matched_keyword','N/A')}\n"
            f"📋 {j.get('description','No description')}\n"
            f"{j.get('posted_ago','')}"
        )
        buttons = [
            [
                InlineKeyboardButton("📄 Proposal", url=j.get("proposal_url", j.get("original_url")) or j.get("url")),
                InlineKeyboardButton("🔗 Original", url=j.get("original_url") or j.get("url")),
            ],
            [
                InlineKeyboardButton("⭐ Save", callback_data=f"job:save:{j.get('id','0')}"),
                InlineKeyboardButton("🗑 Delete", callback_data="job:delete"),
            ],
        ]
        messages.append((msg, buttons))

    if not messages:
        await update.message.reply_text("⚠️ No sample jobs found from any source.")
        return

    for msg, buttons in messages:
        await update.message.reply_text(
            msg, parse_mode="HTML", disable_web_page_preview=False, reply_markup=InlineKeyboardMarkup(buttons)
        )

    log.info(f"Selftest executed by {user.id} ({user.username})")
