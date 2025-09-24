import logging
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler
from db import SessionLocal, User, Keyword, JobSent, SavedJob

logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db = SessionLocal()
    if not db.query(User).filter_by(telegram_id=user_id).first():
        db.add(User(telegram_id=user_id))
        db.commit()
    db.close()
    await update.message.reply_text(
        "👋 Welcome to Freelancer Alerts Bot!\n\n"
        "Commands:\n"
        "/addkeyword <word> → Track jobs by keyword\n"
        "/setcountry <US,UK,DE> → Filter by country list\n"
        "/mysettings → View your filters\n"
        "/savejob <job_id> → Save a job\n"
        "/dismissjob <job_id> → Dismiss/mute a job\n"
        "/clearjob <job_id> → Alias of /dismissjob\n\n"
        "Tip: Job alerts include inline buttons ⭐ Keep / 🙈 Dismiss."
    )

async def addkeyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /addkeyword <keyword>")
        return
    keyword = " ".join(context.args)
    user_id = update.effective_user.id
    db = SessionLocal()
    user = db.query(User).filter_by(telegram_id=user_id).first()
    db.add(Keyword(user_id=user.id, keyword=keyword))
    db.commit()
    db.close()
    await update.message.reply_text(f"✅ Keyword added: {keyword}")

async def setcountry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /setcountry <US,UK,DE>")
        return
    countries = ",".join(context.args).upper().replace(" ", "")
    user_id = update.effective_user.id
    db = SessionLocal()
    user = db.query(User).filter_by(telegram_id=user_id).first()
    user.countries = countries
    db.commit()
    db.close()
    await update.message.reply_text(f"🌍 Countries set: {countries}")

async def mysettings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db = SessionLocal()
    user = db.query(User).filter_by(telegram_id=user_id).first()
    keywords = [k.keyword for k in db.query(Keyword).filter_by(user_id=user.id).all()]
    saved_count = db.query(SavedJob).filter_by(user_id=user.id).count()
    db.close()
    await update.message.reply_text(
        f"🔑 Keywords: {', '.join(keywords) if keywords else 'None'}\n"
        f"🌍 Countries: {user.countries or 'All'}\n"
        f"⭐ Saved jobs: {saved_count}"
    )

async def savejob_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /savejob <job_id>")
        return
    job_id = context.args[0]
    user_id = update.effective_user.id
    db = SessionLocal()
    user = db.query(User).filter_by(telegram_id=user_id).first()
    if not db.query(SavedJob).filter_by(user_id=user.id, job_id=job_id).first():
        db.add(SavedJob(user_id=user.id, job_id=job_id))
        db.commit()
    db.close()
    await update.message.reply_text(f"⭐ Saved job {job_id}")

async def dismissjob_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /dismissjob <job_id>")
        return
    job_id = context.args[0]
    user_id = update.effective_user.id
    db = SessionLocal()
    user = db.query(User).filter_by(telegram_id=user_id).first()
    if not db.query(JobSent).filter_by(user_id=user.id, job_id=job_id).first():
        db.add(JobSent(user_id=user.id, job_id=job_id))
        db.commit()
    db.close()
    await update.message.reply_text(f"🙈 Dismissed job {job_id} (won't notify again)")

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    user_id = q.from_user.id
    db = SessionLocal()
    user = db.query(User).filter_by(telegram_id=user_id).first()
    if data.startswith("save:"):
        jid = data.split(":", 1)[1]
        if not db.query(SavedJob).filter_by(user_id=user.id, job_id=jid).first():
            db.add(SavedJob(user_id=user.id, job_id=jid))
            db.commit()
        await q.edit_message_reply_markup(reply_markup=None)
        await q.message.reply_text(f"⭐ Saved job {jid}")
    elif data.startswith("dismiss:"):
        jid = data.split(":", 1)[1]
        if not db.query(JobSent).filter_by(user_id=user.id, job_id=jid).first():
            db.add(JobSent(user_id=user.id, job_id=jid))
            db.commit()
        await q.edit_message_reply_markup(reply_markup=None)
        await q.message.reply_text(f"🙈 Dismissed job {jid}")
    db.close()

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("addkeyword", addkeyword))
app.add_handler(CommandHandler("setcountry", setcountry))
app.add_handler(CommandHandler("mysettings", mysettings))
app.add_handler(CommandHandler("savejob", savejob_cmd))
app.add_handler(CommandHandler("dismissjob", dismissjob_cmd))
app.add_handler(CommandHandler("clearjob", dismissjob_cmd))  # alias
app.add_handler(CallbackQueryHandler(on_button))

if __name__ == "__main__":
    app.run_polling()
