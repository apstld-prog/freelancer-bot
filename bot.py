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

async def addkeyword_cmd(update, context):
    from sqlalchemy.exc import IntegrityError
    from db import SessionLocal, User, Keyword

    raw_text = (update.message.text or "")
    parts = raw_text.split(maxsplit=1)
    if len(parts) < 2:
        await update.message.reply_text("Usage: /addkeyword python, telegram")
        return

    raw_values = parts[1]
    values = [v.strip() for v in raw_values.split(",") if v.strip()]
    if not values:
        await update.message.reply_text("No keywords provided.")
        return

    tg_id = str(update.effective_user.id)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == tg_id).one_or_none()
        if not user:
            user = User(telegram_id=tg_id)
            db.add(user)
            db.flush()

        added = 0
        for v in values:
            kw = Keyword(user_id=user.id, value=v)
            db.add(kw)
            try:
                db.flush()
                added += 1
            except IntegrityError:
                db.rollback()

        db.commit()
        if added:
            await update.message.reply_text(f"Added {added} keyword(s).")
        else:
            await update.message.reply_text("Nothing new to add.")
    except Exception as e:
        db.rollback()
        await update.message.reply_text(f"⚠️ Error while adding: {e}")
    finally:
        db.close()


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



FX_RATES = {
    "USD": 1.0,
    "EUR": 1.07,
    "GBP": 1.24,
    "CAD": 0.73,
    "AUD": 0.65,
}

def _to_usd(amount, currency):
    if amount is None or not currency:
        return None
    rate = FX_RATES.get(currency.upper())
    if not rate:
        return None
    return round(amount * rate, 2)

def format_budget(bmin, bmax, cur):
    if bmin is None and bmax is None:
        return "Budget: —"
    cur = (cur or "").upper()
    if bmin is not None and bmax is not None:
        base = f"Budget: {bmin:.1f}–{bmax:.1f} {cur}"
    elif bmin is not None:
        base = f"Budget: {bmin:.1f} {cur}"
    else:
        base = f"Budget: up to {bmax:.1f} {cur}"
    if cur != "USD":
        umin = _to_usd(bmin, cur)
        umax = _to_usd(bmax, cur)
        if umin and umax:
            base += f" (~${umin}–${umax})"
        elif umin:
            base += f" (~${umin})"
        elif umax:
            base += f" (~${umax})"
    return base

