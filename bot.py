import logging
import os
from urllib.parse import unquote_plus
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler
from db import SessionLocal, User, Keyword, JobSent, SavedJob

logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("BOT_TOKEN")

DEFAULT_TEMPLATE = (
    "Hello,\n\n"
    "I’m interested in **{job_title}**.\n\n"
    "Why me:\n"
    "• Relevant experience: {experience}\n"
    "• Tech stack: {stack}\n"
    "• Availability: {availability}\n\n"
    "Outline:\n"
    "1) {step1}\n"
    "2) {step2}\n"
    "3) {step3}\n\n"
    "Budget & timeline: {budget_time}\n"
    "Portfolio: {portfolio}\n\n"
    "Regards,\n"
    "{name}\n"
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db = SessionLocal()
    user = db.query(User).filter_by(telegram_id=user_id).first()
    if not user:
        user = User(telegram_id=user_id)
        db.add(user)
        db.commit()
    db.close()
    await update.message.reply_text(
        "👋 Welcome to Freelancer Alerts Bot!\n\n"
        "Commands:\n"
        "/addkeyword <word> → Track jobs by keyword\n"
        "/setcountry <US,UK,DE> → Filter by country list\n"
        "/mysettings → View your filters\n"
        "/setproposal <text> → Save your proposal template\n"
        "   Placeholders you can use: {job_title}, {experience}, {stack}, {availability}, {step1}, {step2}, {step3}, {budget_time}, {portfolio}, {name}\n"
        "/savejob <job_id> → Save a job\n"
        "/dismissjob <job_id> → Dismiss/mute a job\n"
        "/clearjob <job_id> → Alias of /dismissjob\n\n"
        "Tip: Job alerts include inline buttons ⭐ Keep / 🙈 Dismiss / ✍️ Proposal."
    )

async def addkeyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /addkeyword <keyword>")
        return
    keyword = " ".join(context.args)
    user_id = update.effective_user.id
    db = SessionLocal()
    user = db.query(User).filter_by(telegram_id=user_id).first()
    exists = db.query(Keyword).filter_by(user_id=user.id, keyword=keyword).first()
    if not exists:
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
        f"⭐ Saved jobs: {saved_count}\n"
        f"📝 Has proposal template: {'Yes' if user.proposal_template else 'No'}"
    )

async def setproposal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save user's proposal template (full text after the command)."""
    user_id = update.effective_user.id
    text = (update.message.text or "").split(" ", 1)
    if len(text) < 2 or not text[1].strip():
        await update.message.reply_text(
            "Usage: /setproposal <your template text>\n\n"
            "Example:\n"
            "/setproposal Hello, I can help with {job_title}. I have {experience} and use {stack}. Budget/time: {budget_time}.\n"
            "Portfolio: {portfolio}\n"
            "Thanks, {name}"
        )
        return
    template = text[1].strip()
    db = SessionLocal()
    user = db.query(User).filter_by(telegram_id=user_id).first()
    user.proposal_template = template
    db.commit()
    db.close()
    await update.message.reply_text("✅ Proposal template saved.")

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

    elif data.startswith("proposal:"):
        # data format: proposal:<job_id>|<platform>|<affiliate_link>|<encoded_title>
        payload = data.split(":", 1)[1]
        parts = payload.split("|")
        job_id = parts[0] if len(parts) > 0 else ""
        platform = parts[1] if len(parts) > 1 else ""
        link = parts[2] if len(parts) > 2 else ""
        job_title = unquote_plus(parts[3]) if len(parts) > 3 else "the job"

        template = user.proposal_template or DEFAULT_TEMPLATE
        # Replace placeholders with simple defaults; user can customize via /setproposal
        filled = template.format(
            job_title=job_title,
            experience="3+ years with similar projects",
            stack="Python, Telegram, APIs",
            availability="immediately",
            step1="Clarify requirements",
            step2="Implement & test",
            step3="Deliver & support",
            budget_time="to be discussed after details",
            portfolio="(link here)",
            name=q.from_user.first_name or "Freelancer",
        )

        await q.message.reply_text(
            "✍️ *Your Proposal Draft* (copy & paste into the platform):\n\n" + filled,
            parse_mode="Markdown"
        )

    db.close()

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("addkeyword", addkeyword))
app.add_handler(CommandHandler("setcountry", setcountry))
app.add_handler(CommandHandler("mysettings", mysettings))
app.add_handler(CommandHandler("setproposal", setproposal))
app.add_handler(CommandHandler("savejob", savejob_cmd))
app.add_handler(CommandHandler("dismissjob", dismissjob_cmd))
app.add_handler(CommandHandler("clearjob", dismissjob_cmd))  # alias
app.add_handler(CallbackQueryHandler(on_button))

if __name__ == "__main__":
    app.run_polling()
