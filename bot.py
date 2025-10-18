# bot.py (patched /selftest) - minimal extract for replacement
import os, logging, asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from db_events import ensure_feed_events_schema, record_event

log = logging.getLogger("bot")

async def selftest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        job_text = (
            "<b>Email Signature from Existing Logo</b>\n"
            "<b>Budget:</b> 10.0–30.0 USD\n"
            "<b>Source:</b> Freelancer\n"
            "<b>Match:</b> logo\n"
            "✏️ Please create an editable version of the email signature based on the provided logo.\n"
        )
        url = "https://www.freelancer.com/projects/sample"
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("📄 Proposal", url=url),
            InlineKeyboardButton("🔗 Original", url=url)
        ],[
            InlineKeyboardButton("⭐ Save", callback_data="job:save"),
            InlineKeyboardButton("🗑️ Delete", callback_data="job:delete")
        ]])
        await update.effective_chat.send_message(job_text, parse_mode=ParseMode.HTML, reply_markup=kb)
        await asyncio.sleep(0.4)
        pph_text = (
            "<b>Logo Design for New Startup</b>\n"
            "<b>Budget:</b> 50.0–120.0 GBP (~$60–$145 USD)\n"
            "<b>Source:</b> PeoplePerHour\n"
            "<b>Match:</b> logo\n"
            "🎨 Create a modern, minimal logo for a UK startup. Provide vector files.\n"
        )
        pph_url = "https://www.peopleperhour.com/freelance-jobs/sample"
        pph_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("📄 Proposal", url=pph_url),
            InlineKeyboardButton("🔗 Original", url=pph_url)
        ],[
            InlineKeyboardButton("⭐ Save", callback_data="job:save"),
            InlineKeyboardButton("🗑️ Delete", callback_data="job:delete")
        ]])
        await update.effective_chat.send_message(pph_text, parse_mode=ParseMode.HTML, reply_markup=pph_kb)
        try:
            ensure_feed_events_schema()
            record_event('freelancer'); record_event('peopleperhour')
        except Exception: pass
    except Exception as e:
        log.exception("selftest failed: %s", e)
