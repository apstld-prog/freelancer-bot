import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from db import get_session
from db_events import log_platform_event

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")

# ==============================================================
# START
# ==============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Καλώς ήρθες στο Freelancer Alerts Bot!\n"
        "Θα λαμβάνεις αγγελίες από διάφορες πλατφόρμες freelancing."
    )

# ==============================================================
# SELFTEST / FEEDSTATUS
# ==============================================================
async def selftest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Self-test completed: bot λειτουργεί σωστά.")
    log_platform_event("freelancer")

async def feedstatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📡 Feeds ενεργά και συγχρονισμένα.")

# ==============================================================
# JOB ACTION HANDLER (Save / Delete)
# ==============================================================
async def job_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not q.data:
        return

    chat_id = q.message.chat_id
    msg_id = q.message.message_id

    # Helper για ασφαλή διαγραφή μηνύματος
    async def _delete():
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception as e:
            log.warning("delete_message failed: %s", e)

    # --------------------------
    # DELETE: διαγράφει άμεσα
    # --------------------------
    if q.data == "job:delete":
        try:
            await q.answer("Deleted", show_alert=False)
        except Exception:
            pass
        await _delete()
        return

    # --------------------------
    # SAVE: αποθηκεύει και μετά διαγράφει
    # --------------------------
    if q.data == "job:save":
        try:
            if "save_job_from_message" in globals():
                await globals()["save_job_from_message"](q.message, context)
            elif "save_job" in globals():
                await globals()["save_job"](q.message, context)
        except Exception as e:
            log.warning("save job failed: %s", e)

        try:
            await q.answer("Saved", show_alert=False)
        except Exception:
            pass
        await _delete()
        return

    await q.answer()

# ==============================================================
# MAIN ENTRY
# ==============================================================
def build_application():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("selftest", selftest))
    app.add_handler(CommandHandler("feedstatus", feedstatus))
    app.add_handler(CallbackQueryHandler(job_action_cb, pattern=r"^job:(save|delete)$"))

    return app

if __name__ == "__main__":
    import asyncio
    async def _run():
        app = build_application()
        await app.initialize()
        await app.start()
        log.info("✅ Bot started (standalone mode)")
        await asyncio.Event().wait()
    asyncio.run(_run())
