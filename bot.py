# bot.py
import os, datetime, logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from sqlalchemy import text
from db import get_session
from config import convert_to_usd, posted_ago

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 5254014824

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Welcome! You’ll start receiving job alerts soon.")

async def selftest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_ID:
        return await update.message.reply_text("Unauthorized.")
    from worker import run_pipeline
    items = run_pipeline([])
    if not items:
        return await update.message.reply_text("No jobs found.")
    for it in items[:5]:
        await send_job(update.effective_chat.id, it)

async def send_job(chat_id, job):
    from config import FREELANCER_URL
    title = job.get("title", "")
    desc = job.get("description", "")
    cur = job.get("currency", "USD")
    bmin, bmax = job.get("budget_min"), job.get("budget_max")
    if bmin:
        usd_min = convert_to_usd(bmin, cur)
        usd_max = convert_to_usd(bmax, cur) if bmax else usd_min
        budget_str = f"{cur} {bmin}-{bmax} ({usd_min}-{usd_max} USD)"
    else:
        budget_str = "N/A"
    link = job.get("original_url")
    posted = posted_ago(job.get("created_at"))
    text = f"<b>{title}</b>\n💰 {budget_str}\n🕒 {posted}\n\n{desc[:400]}...\n\n<a href='{link}'>View job</a>"
    kb = [[
        InlineKeyboardButton("💾 Save", callback_data="job:save"),
        InlineKeyboardButton("❌ Delete", callback_data="job:delete"),
    ]]
    await context.bot.send_message(chat_id, text, parse_mode="HTML",
                                   disable_web_page_preview=False,
                                   reply_markup=InlineKeyboardMarkup(kb))

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    uid = q.from_user.id
    s = get_session()
    if data == "job:save":
        s.execute(text("INSERT INTO saved_job (user_id, job_id, saved_at) VALUES (:u,:j,NOW()) ON CONFLICT DO NOTHING"),
                  {"u": uid, "j": "temp"})
        s.commit()
        await q.answer("✅ Saved")
    elif data == "job:delete":
        await context.bot.delete_message(uid, q.message.message_id)
        await q.answer("🗑️ Deleted")

async def saved(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_chat.id
    s = get_session()
    rows = s.execute(text("""
        SELECT je.title, je.affiliate_url, je.budget_amount, je.budget_currency, je.budget_usd, je.created_at
        FROM saved_job sj
        JOIN job_event je ON je.id=sj.job_id
        WHERE sj.user_id=:u
        ORDER BY sj.saved_at DESC LIMIT 10
    """), {"u": uid}).fetchall()
    if not rows:
        return await update.message.reply_text("Saved list is empty.")
    txt = "💾 <b>Saved Jobs</b>\n\n" + "\n\n".join(
        [f"• <b>{r[0]}</b>\n💰 {r[3]} {r[2]} ({r[4]} USD)\n🕒 {posted_ago(r[5])}" for r in rows])
    await update.message.reply_text(txt, parse_mode="HTML")

def build_application():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("selftest", selftest))
    app.add_handler(CommandHandler("saved", saved))
    app.add_handler(CallbackQueryHandler(on_callback))
    return app

if __name__ == "__main__":
    app = build_application()
    log.info("Starting bot polling…")
    app.run_polling()
