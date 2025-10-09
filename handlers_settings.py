
from telegram import Update
from telegram.ext import ContextTypes
from ui_texts import settings_text
from db import SessionLocal, User  # assumes existing db.py

async def mysettings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    with SessionLocal() as s:
        user = s.query(User).filter(User.telegram_id == uid).first()
    if not user:
        await update.effective_chat.send_message("No settings yet. Use /addkeyword to start.")
        return
    text = settings_text(
        keywords=user.keywords or [],
        countries=user.countries or "ALL",
        proposal_template=user.proposal_template,
        trial_start=getattr(user, "trial_start", None),
        trial_end=getattr(user, "trial_end", None),
        license_until=getattr(user, "license_until", None),
        active=bool(user.is_active),
        blocked=bool(user.is_blocked),
    )
    await update.effective_chat.send_message(text, parse_mode="HTML")
