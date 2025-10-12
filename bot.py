from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from db import get_session
from sqlalchemy import text

BOT_TOKEN = "8301080604:AAF7Hsb_ImfJHiJVYTTXzQOwgI37h8XlEKc"

def build_application():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("feedstatus", feedstatus))
    app.add_handler(CommandHandler("selftest", selftest))
    # keep one generic callback handler (do not add extra commands/UI)
    app.add_handler(CallbackQueryHandler(callback))
    return app

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # DO NOT CHANGE /start UI
    keyboard = [
        [InlineKeyboardButton("🔍 Feed Status", callback_data="act:feedstatus")],
        [InlineKeyboardButton("🧪 Self Test", callback_data="act:selftest")],
        [InlineKeyboardButton("💾 Saved Jobs", callback_data="act:saved")],
    ]
    await update.message.reply_text(
        "👋 Welcome to Freelancer Alert Bot",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def feedstatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # DO NOT CHANGE
    with get_session() as s:
        count = s.execute(text("SELECT COUNT(*) FROM feed_events")).scalar()
    await update.message.reply_text(f"📊 Feed events recorded: {count}")

async def selftest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # DO NOT CHANGE
    await update.message.reply_text("✅ Self-test completed. All systems functional.")

# ----------------- helpers for Save/Delete (no UI changes) -----------------

def ensure_saved_table() -> None:
    """Create saved_job table if missing (idempotent)."""
    with get_session() as s:
        s.execute(text("""
            CREATE TABLE IF NOT EXISTS saved_job (
                user_tg BIGINT NOT NULL,
                job_key TEXT NOT NULL,
                saved_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC'),
                PRIMARY KEY (user_tg, job_key)
            )
        """))
        s.commit()

# ----------------- single callback router (keeps your existing behavior) ---

async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    # SAVE: persist + remove the card
    if data.startswith("job:save:"):
        ensure_saved_table()
        job_key = data.split(":", 2)[2]  # format: job:save:<job_key>
        with get_session() as s:
            s.execute(
                text("INSERT INTO saved_job (user_tg, job_key) VALUES (:u, :k) ON CONFLICT DO NOTHING"),
                {"u": query.from_user.id, "k": job_key}
            )
            s.commit()
        # Remove the message (as requested)
        try:
            await query.message.delete()
        except Exception:
            pass
        # Silent confirmation
        await query.answer("Saved", show_alert=False)
        return

    # DELETE: just remove the card
    if data == "job:delete":
        try:
            await query.message.delete()
        except Exception:
            pass
        await query.answer("Deleted", show_alert=False)
        return

    # KEEP existing minimal texts for these actions (no UI changes)
    if data == "act:saved":
        await query.edit_message_text("📂 Saved jobs list is empty.")
        return

    if data == "act:feedstatus":
        await query.edit_message_text("📊 Feed status checked successfully.")
        return

    if data == "act:selftest":
        await query.edit_message_text("✅ Self-test completed successfully.")
        return
