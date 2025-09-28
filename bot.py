import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import joinedload

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    constants,
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from db import SessionLocal, User, Keyword, JobSaved, JobDismissed

# ---------------- Logging ----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [bot] %(levelname)s: %(message)s")
logger = logging.getLogger("bot")

# ---------------- Config ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

TRIAL_DAYS = int(os.getenv("TRIAL_DAYS", "10"))

# ---------------- Helpers ----------------
def now_utc():
    return datetime.now(timezone.utc)

async def ensure_user(db, tg_id: int) -> User:
    user = db.query(User).filter_by(telegram_id=str(tg_id)).first()
    if not user:
        user = User(telegram_id=str(tg_id), trial_until=now_utc() + timedelta(days=TRIAL_DAYS))
        db.add(user)
        db.commit()
        db.refresh(user)
    return user

def is_admin(update: Update) -> bool:
    return update.effective_user and update.effective_user.id == ADMIN_ID

# ---------------- Commands ----------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        user = await ensure_user(db, update.effective_user.id)
        await update.message.reply_text(
            "👋 Welcome to Freelancer Alert Bot!\n\n"
            f"🎁 You have a *{TRIAL_DAYS}-day free trial*.\n"
            "Use /help to see how it works.",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
    finally:
        db.close()

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (
        "📖 *Help / How it works*\n\n"
        "1️⃣ Add keywords with /addkeyword python telegram\n"
        "2️⃣ Set countries with /setcountry US,UK (or ALL)\n"
        "3️⃣ Save a proposal template with /setproposal <text>\n"
        "   Placeholders: {jobtitle}, {experience}, {stack}, {budgettime}, {portfolio}, {name}\n"
        "4️⃣ When a job arrives you can:\n"
        "   ⭐ Keep it\n"
        "   🗑 Delete it\n"
        "   💼 Proposal → direct affiliate link\n"
        "   🔗 Original → affiliate-wrapped job link\n\n"
        "/mysettings to check filters\n"
        "/selftest for a test job\n"
        "/platforms CC to see platforms per country (e.g. /platforms GR)\n\n"
        "🔹 Platforms currently supported:\n"
        "   • Freelancer.com, Fiverr Affiliates\n"
        "   • PeoplePerHour (UK), Malt (FR/EU), Workana (ES/EU/LatAm), Upwork\n"
        "   • Greek Boards: JobFind.gr, Skywalker.gr, Kariera.gr"
    )
    await update.message.reply_text(txt, parse_mode=constants.ParseMode.MARKDOWN)

async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    txt = f"🆔 Your Telegram ID: `{u.id}`\n👤 Name: {u.full_name}\n"
    if u.username:
        txt += f"🔗 Username: @{u.username}\n"
    else:
        txt += f"🔗 Username: (none)\n"
    if is_admin(update):
        txt += "\n⭐ You are *ADMIN*."
    await update.message.reply_text(txt, parse_mode=constants.ParseMode.MARKDOWN)

async def selftest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    kw = "TESTKEY"
    job_id = f"test-{kw.lower()}"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💼 Proposal", url="https://freelancer.com")],
        [InlineKeyboardButton("⭐ Keep", callback_data=f"save:{job_id}"),
         InlineKeyboardButton("🗑 Delete", callback_data=f"dismiss:{job_id}")]
    ])
    await update.message.reply_text(
        f"🧪 [TEST] Job matched keyword: {kw}\n\nThis is a test message.",
        reply_markup=kb
    )

async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        user = await ensure_user(db, update.effective_user.id)
        kws = [k.keyword for k in user.keywords]
        trial = user.trial_until.strftime("%Y-%m-%d") if user.trial_until else "None"
        license = user.access_until.strftime("%Y-%m-%d") if user.access_until else "None"
        txt = (
            f"🔑 Keywords: {', '.join(kws) if kws else '(none)'}\n"
            f"🎁 Trial until: {trial}\n"
            f"🔒 License until: {license}\n"
        )
        await update.message.reply_text(txt)
    finally:
        db.close()

# ---------------- Keyword commands ----------------
async def addkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Usage: /addkeyword <kw1> <kw2> ...")
    db = SessionLocal()
    try:
        user = await ensure_user(db, update.effective_user.id)
        for kw in context.args:
            if not db.query(Keyword).filter_by(user_id=user.id, keyword=kw).first():
                db.add(Keyword(user_id=user.id, keyword=kw))
        db.commit()
        await update.message.reply_text("✅ Keywords added.")
    finally:
        db.close()

async def listkeywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        user = await ensure_user(db, update.effective_user.id)
        kws = [k.keyword for k in user.keywords]
        await update.message.reply_text(f"Your keywords: {', '.join(kws) if kws else '(none)'}")
    finally:
        db.close()

async def delkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Usage: /delkeyword <keyword>")
    kw = context.args[0]
    db = SessionLocal()
    try:
        user = await ensure_user(db, update.effective_user.id)
        obj = db.query(Keyword).filter_by(user_id=user.id, keyword=kw).first()
        if obj:
            db.delete(obj)
            db.commit()
            await update.message.reply_text(f"Deleted keyword '{kw}'.")
        else:
            await update.message.reply_text(f"No such keyword '{kw}'.")
    finally:
        db.close()

async def clearkeywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        user = await ensure_user(db, update.effective_user.id)
        for k in user.keywords:
            db.delete(k)
        db.commit()
        await update.message.reply_text("All keywords cleared.")
    finally:
        db.close()

# ---------------- Keep / Delete Callbacks ----------------
async def save_job_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, job_id = q.data.split(":", 1)
    db = SessionLocal()
    try:
        user = await ensure_user(db, update.effective_user.id)
        if not db.query(JobSaved).filter_by(user_id=user.id, job_id=job_id).first():
            db.add(JobSaved(user_id=user.id, job_id=job_id))
            db.commit()
        await q.answer("Saved ✅", show_alert=False)
    finally:
        db.close()

async def dismiss_job_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, job_id = q.data.split(":", 1)
    db = SessionLocal()
    try:
        user = await ensure_user(db, update.effective_user.id)
        if not db.query(JobDismissed).filter_by(user_id=user.id, job_id=job_id).first():
            db.add(JobDismissed(user_id=user.id, job_id=job_id))
            db.commit()
    finally:
        db.close()
    try:
        await q.message.delete()
    except Exception:
        pass

# ---------------- Admin ----------------
async def admin_users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    db = SessionLocal()
    try:
        users = db.query(User).all()
        txt = f"👥 Total users: {len(users)}\n"
        for u in users[:20]:
            txt += f"- {u.telegram_id}, trial={u.trial_until}, license={u.access_until}\n"
        await update.message.reply_text(txt)
    finally:
        db.close()

async def grant_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if len(context.args) < 2:
        return await update.message.reply_text("Usage: /grant <telegram_id> <days>")
    uid, days = context.args[0], int(context.args[1])
    db = SessionLocal()
    try:
        u = db.query(User).filter_by(telegram_id=uid).first()
        if not u:
            return await update.message.reply_text("User not found.")
        u.access_until = now_utc() + timedelta(days=days)
        db.commit()
        await update.message.reply_text(f"Granted {days} days to {uid}.")
    finally:
        db.close()

# ---------------- Application ----------------
def build_application() -> Application:
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("whoami", whoami_cmd))
    app.add_handler(CommandHandler("selftest", selftest_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))

    app.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app.add_handler(CommandHandler("listkeywords", listkeywords_cmd))
    app.add_handler(CommandHandler("delkeyword", delkeyword_cmd))
    app.add_handler(CommandHandler("clearkeywords", clearkeywords_cmd))

    app.add_handler(CommandHandler("admin_users", admin_users_cmd))
    app.add_handler(CommandHandler("grant", grant_cmd))

    # Callbacks
    app.add_handler(CallbackQueryHandler(save_job_cb, pattern=r"^save:.+"))
    app.add_handler(CallbackQueryHandler(dismiss_job_cb, pattern=r"^dismiss:.+"))

    return app

if __name__ == "__main__":
    app = build_application()
    app.run_polling()
