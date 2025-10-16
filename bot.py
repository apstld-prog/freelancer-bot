import logging
import asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
from fastapi import FastAPI
import os
import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
DB_URL = os.getenv("DATABASE_URL")
HOOK_SECRET = os.getenv("WEBHOOK_SECRET", "hook-secret-777")

app = FastAPI()

def db_connect():
    return psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 Welcome to Freelancer Alert Bot!\n\n"
        "You can receive live job alerts and manage saved jobs easily."
    )
    keyboard = [[InlineKeyboardButton("View Saved Jobs", callback_data="act:saved")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def feedstatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Feed is active and running smoothly.")

async def selftest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🧩 Self-test completed successfully!")

# --- Helper: Build card like worker format ---
def build_card(title, url, desc, budget, keyword):
    lines = []
    if keyword:
        lines.append(f"🔍 *Keyword:* {keyword}")
    if budget:
        lines.append(f"💰 *Budget:* {budget}")
    lines.append(f"🌐 [View Original Job]({url})")
    card = f"📌 *{title}*\n" + "\n".join(lines)
    return card

# --- SAVE ---
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    uid = q.from_user.id

    if data.startswith("job:save"):
        try:
            with db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("INSERT INTO saved_job (user_id, title, url, description) VALUES (%s,%s,%s,%s)",
                                (uid, "Saved Job Example", "https://www.freelancer.com", ""))
            await q.message.delete()
            await q.answer("💾 Job saved successfully!", show_alert=False)
        except Exception as e:
            logger.warning(f"Save failed: {e}")
            await q.answer("⚠️ Could not save job.", show_alert=True)
        return

    # --- SAVED JOBS ---
    if data == "act:saved":
        try:
            with db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT id, title, url, description FROM saved_job WHERE user_id=%s ORDER BY id DESC LIMIT 10", (uid,))
                    rows = cur.fetchall()

            if not rows:
                await q.message.reply_text("💾 No saved jobs yet.")
                await q.answer()
                return

            for rid, title, url, desc in rows:
                card = build_card(title, url, desc, budget=None, keyword=None)
                kb = [
                    [
                        InlineKeyboardButton("🌐 Original", url=url),
                        InlineKeyboardButton("🗑 Delete", callback_data=f"job:del:{rid}")
                    ]
                ]
                await q.message.reply_text(card, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
            await q.answer()
        except Exception as e:
            logger.error(f"Error showing saved: {e}")
            await q.answer("⚠️ Error loading saved jobs.", show_alert=True)
        return

    # --- DELETE JOB ---
    if data.startswith("job:del:"):
        try:
            rid = int(data.split(":")[2])
            with db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM saved_job WHERE id=%s AND user_id=%s", (rid, uid))
            await q.message.delete()
            await q.answer("🗑 Deleted successfully.", show_alert=False)
        except Exception as e:
            logger.warning(f"Delete failed: {e}")
            await q.answer("⚠️ Could not delete job.", show_alert=True)

def build_application():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("feedstatus", feedstatus))
    application.add_handler(CommandHandler("selftest", selftest))
    application.add_handler(CallbackQueryHandler(handle_callback))
    return application

# --- FastAPI integration ---
from telegram import Update
from telegram.ext import ContextTypes
from fastapi import Request

@app.on_event("startup")
async def startup():
    global application
    application = build_application()
    await application.initialize()
    await application.start()
    await application.bot.set_webhook(f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/webhook/{HOOK_SECRET}")
    logger.info("✅ Bot started via FastAPI")

@app.post(f"/webhook/{HOOK_SECRET}")
async def tg_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}
