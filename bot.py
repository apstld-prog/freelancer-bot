import os, asyncio, logging, httpx
from datetime import datetime, timedelta, timezone
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes
)
from sqlalchemy import text
from db import SessionLocal, User, Keyword, Job
from utils import now_utc, _uid_field, DEFAULT_TRIAL_DAYS

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

# ----------------------------------------------------------
# BASIC MENU HANDLERS
# ----------------------------------------------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to Freelancer Alert Bot!\n\n"
        "🎁 You have a 10-day free trial.\n"
        "Automatically finds matching freelance jobs and sends instant alerts.\n\n"
        "Use /help to see how it works."
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ Available commands:\n"
        "/addkeyword <words> — Add new keywords\n"
        "/mysettings — View your current settings\n"
        "/feedstatus — Job feeds activity (admin)\n"
        "/contact — Contact the admin"
    )

# ----------------------------------------------------------
# ADD KEYWORDS COMMAND
# ----------------------------------------------------------
async def addkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add comma-separated keywords for the current user."""
    try:
        _ = SessionLocal
        _ = User
        _ = Keyword
    except NameError:
        if getattr(update, "message", None):
            await update.message.reply_text("Database unavailable.")
        return

    raw = ""
    if getattr(context, "args", None):
        raw = " ".join(context.args)
    if not raw and getattr(update, "message", None) and getattr(update.message, "text", ""):
        raw = update.message.text.replace("/addkeyword", "").strip()

    if not raw:
        if getattr(update, "message", None):
            await update.message.reply_text("Please provide at least one keyword separated by commas.")
        return

    kws = [k.strip().lower() for k in raw.split(",") if k.strip()]
    if not kws:
        if getattr(update, "message", None):
            await update.message.reply_text("No valid keywords found.")
        return

    db = SessionLocal()
    try:
        tg_id = str(update.effective_user.id)
        try:
            uid_field = _uid_field()
        except Exception:
            uid_field = "telegram_id"

        u = db.query(User).filter(getattr(User, uid_field) == tg_id).one_or_none()
        if not u:
            u = User(
                telegram_id=tg_id,
                started_at=now_utc(),
                trial_until=now_utc() + timedelta(days=DEFAULT_TRIAL_DAYS),
                is_blocked=False,
            )
            db.add(u)
            db.commit()
            db.refresh(u)

        added = []
        for kw in kws:
            exists = db.query(Keyword).filter_by(user_id=u.id, keyword=kw).first()
            if not exists:
                db.add(Keyword(user_id=u.id, keyword=kw, created_at=now_utc()))
                added.append(kw)
        db.commit()

        if getattr(update, "message", None):
            if added:
                await update.message.reply_text(f"✅ Added keywords: {', '.join(added)}")
            else:
                await update.message.reply_text("No new keywords were added.")
    except Exception as e:
        db.rollback()
        await update.message.reply_text(f"⚠️ Error while adding: {e}")
    finally:
        db.close()

# ----------------------------------------------------------
# SETTINGS COMMAND
# ----------------------------------------------------------
async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    tg_id = str(update.effective_user.id)
    try:
        u = db.query(User).filter(User.telegram_id == tg_id).one_or_none()
        kws = db.query(Keyword.keyword).filter(Keyword.user_id == u.id).all() if u else []
        kws_list = ", ".join([k[0] for k in kws]) if kws else "(none)"
        txt = (
            "🛠 <b>Your Settings</b>\n"
            f"• <b>Keywords:</b> {kws_list}\n"
            "• <b>Countries:</b> ALL\n"
            "• <b>Proposal template:</b> (none)\n\n"
        )
        if u:
            txt += (
                f"Trial start: {u.started_at}\n"
                f"Trial end: {u.trial_until}\n"
                f"License until: {u.license_until}\n"
                f"Active: {'✅' if not u.is_blocked else '❌'}\n\n"
            )
        txt += (
            "Platforms monitored:\n"
            "Freelancer.com, PeoplePerHour, Malt, Workana, Guru, 99designs, "
            "Toptal, Codeable, YunoJuno, Worksome, twago, freelancermap\n"
            "Greece: JobFind.gr, Skywalker.gr, Kariera.gr"
        )
        await update.message.reply_text(txt, parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {e}")
    finally:
        db.close()

# ----------------------------------------------------------
# FEEDSTATUS (ADMIN)
# ----------------------------------------------------------
async def feedstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        q = text(
            "SELECT j.source, COUNT(*) AS c FROM job j "
            "WHERE j.created_at > :d GROUP BY j.source"
        )
        r = db.execute(q, {"d": now_utc() - timedelta(days=1)}).fetchall()
        if not r:
            await update.message.reply_text("No data in last 24h.")
            return
        txt = "📊 <b>Sent jobs by platform (last 24h)</b>\n"
        for row in r:
            txt += f"• {row[0]}: {row[1]}\n"
        await update.message.reply_text(txt, parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {e}")
    finally:
        db.close()

# ----------------------------------------------------------
# CONTACT / ADMIN REPLY FLOW (stub)
# ----------------------------------------------------------
async def contact_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✉️ Type your message and it will be sent to the admin.")

# ----------------------------------------------------------
# BUILD APPLICATION
# ----------------------------------------------------------
def build_application():
    app = ApplicationBuilder().token(os.getenv("BOT_TOKEN")).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))
    app.add_handler(CommandHandler("feedstatus", feedstatus_cmd))
    app.add_handler(CommandHandler("contact", contact_cmd))

    return app

if __name__ == "__main__":
    app = build_application()
    log.info("Starting bot...")
    app.run_polling()
