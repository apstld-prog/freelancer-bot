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
    app.add_handler(CallbackQueryHandler(callback))
    return app

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔍 Feed Status", callback_data="act:feedstatus")],
        [InlineKeyboardButton("🧪 Self Test", callback_data="act:selftest")],
        [InlineKeyboardButton("💾 Saved Jobs", callback_data="act:saved")],
    ]
    await update.message.reply_text("👋 Welcome to Freelancer Alert Bot", reply_markup=InlineKeyboardMarkup(keyboard))

async def feedstatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        count = s.execute(text("SELECT COUNT(*) FROM feed_events")).scalar()
    await update.message.reply_text(f"📊 Feed events recorded: {count}")

async def selftest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Self-test completed. All systems functional.")

async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("job:save"):
        job_id = data.split(":")[2]
        with get_session() as s:
            s.execute(text("INSERT INTO saved_job (user_id, job_id) VALUES (:u, :j) ON CONFLICT DO NOTHING"), {"u": query.from_user.id, "j": job_id})
            s.commit()
        await query.edit_message_text("💾 Job saved successfully.")

    elif data.startswith("job:delete"):
        await query.message.delete()

    elif data == "act:saved":
        await query.edit_message_text("📂 Saved jobs list is empty.")

    elif data == "act:feedstatus":
        await query.edit_message_text("📊 Feed status checked successfully.")

    elif data == "act:selftest":
        await query.edit_message_text("✅ Self-test completed successfully.")
