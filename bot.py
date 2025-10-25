import logging
import os
from datetime import datetime
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from db import get_user_list
from utils import send_job_to_user
from platform_freelancer import fetch_freelancer_jobs
from platform_peopleperhour import fetch_pph_jobs
from db_events import ensure_feed_events_schema

# -------------------------------------------------------
# Logger setup
# -------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("bot")

# -------------------------------------------------------
# Environment token
# -------------------------------------------------------
TOKEN = (
    os.getenv("TELEGRAM_BOT_TOKEN")
    or os.getenv("TELEGRAM_TOKEN")
    or os.getenv("BOT_TOKEN")
)
if not TOKEN:
    logger.error("❌ Missing TELEGRAM_BOT_TOKEN in environment!")
    raise SystemExit("Missing TELEGRAM_BOT_TOKEN")

# -------------------------------------------------------
# Core Commands
# -------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command."""
    keyboard = [
        [InlineKeyboardButton("🧠 Selftest", callback_data="selftest")],
        [InlineKeyboardButton("📡 Feed Status", callback_data="feedstatus")],
    ]
    text = (
        "👋 <b>Welcome to Freelancer Alert Bot</b>\n\n"
        "You’ll receive job alerts from:\n"
        "• Freelancer.com\n"
        "• PeoplePerHour\n\n"
        "Use /selftest anytime to verify sources are active."
    )
    await update.message.reply_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
    )


async def feedstatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current platform feed status."""
    text = (
        "<b>Platform Feed Status</b>\n"
        "✅ Freelancer.com - OK\n"
        "✅ PeoplePerHour - OK\n"
        "🟡 Skywalker - temporarily paused\n"
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard callbacks."""
    query = update.callback_query
    await query.answer()

    if query.data == "selftest":
        await send_selftest(query, context)
    elif query.data == "feedstatus":
        await feedstatus(query, context)
    elif query.data.startswith("save_"):
        await query.edit_message_reply_markup(
            InlineKeyboardMarkup(
                [[InlineKeyboardButton("✅ Saved", callback_data="ok_saved")]]
            )
        )
    elif query.data.startswith("delete_"):
        await query.edit_message_reply_markup(
            InlineKeyboardMarkup(
                [[InlineKeyboardButton("🗑️ Deleted", callback_data="ok_deleted")]]
            )
        )
    else:
        await query.answer("Unknown action")


# -------------------------------------------------------
# Selftest command
# -------------------------------------------------------
async def selftest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manual /selftest command."""
    await send_selftest(update, context)


async def send_selftest(update_or_query, context: ContextTypes.DEFAULT_TYPE):
    """Send one job from each platform to confirm operation."""
    try:
        chat_id = (
            update_or_query.effective_chat.id
            if update_or_query.effective_chat
            else update_or_query.message.chat_id
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text="🧠 Running self-test... please wait a few seconds.",
        )

        test_kw = "logo"
        fl_jobs = await fetch_freelancer_jobs(test_kw)
        pph_jobs = await fetch_pph_jobs(test_kw)

        if fl_jobs:
            job = fl_jobs[0]
            job["matched_keyword"] = test_kw
            await send_job_to_user(context.bot, chat_id, job)
        else:
            await context.bot.send_message(chat_id=chat_id, text="❌ No Freelancer job found.")

        if pph_jobs:
            job = pph_jobs[0]
            job["matched_keyword"] = test_kw
            await send_job_to_user(context.bot, chat_id, job)
        else:
            await context.bot.send_message(chat_id=chat_id, text="❌ No PeoplePerHour job found.")

        await context.bot.send_message(chat_id=chat_id, text="✅ Self-test complete.")
    except Exception as e:
        logger.error(f"[Selftest] Error: {e}")
        await context.bot.send_message(
            chat_id=chat_id, text=f"❌ Self-test error: {e}"
        )


# -------------------------------------------------------
# Application Builder
# -------------------------------------------------------
def build_application() -> Application:
    ensure_feed_events_schema()
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("feedstatus", feedstatus))
    app.add_handler(CommandHandler("selftest", selftest))
    app.add_handler(CallbackQueryHandler(handle_callback))

    return app


# -------------------------------------------------------
# FastAPI entry point (Render runs uvicorn with this)
# -------------------------------------------------------
if __name__ == "__main__":
    from telegram.ext import ApplicationBuilder

    logger.info("🚀 Starting bot in standalone mode...")
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("feedstatus", feedstatus))
    application.add_handler(CommandHandler("selftest", selftest))
    application.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("✅ Bot is polling...")
    application.run_polling()
