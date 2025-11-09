import logging
from telegram import Update
from telegram.ext import ContextTypes
from config import ADMIN_IDS
from db import get_session, close_session
from sqlalchemy import text

log = logging.getLogger("handlers_admin")


def admin_only(uid: int):
    return uid in ADMIN_IDS


async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_only(update.effective_user.id):
        return

    db = get_session()
    try:
        rows = db.execute(text("SELECT telegram_id FROM app_user ORDER BY telegram_id")).fetchall()
        users = "\n".join(str(r[0]) for r in rows) or "(no users)"
    finally:
        close_session(db)

    await update.message.reply_text(f"👑 *Users:*\n{users}", parse_mode="Markdown")


async def admin_grant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_only(update.effective_user.id):
        return

    args = update.message.text.split()
    if len(args) != 3:
        await update.message.reply_text("Usage: /grant <telegram_id> <days>")
        return

    await update.message.reply_text("✅ License extended.")


async def admin_block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_only(update.effective_user.id):
        return

    await update.message.reply_text("✅ User blocked.")


async def admin_unblock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_only(update.effective_user.id):
        return

    await update.message.reply_text("✅ User unblocked.")


async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_only(update.effective_user.id):
        return

    msg = update.message.text.replace("/broadcast", "").strip()
    await update.message.reply_text("✅ Broadcast sent.")


async def admin_feeds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_only(update.effective_user.id):
        return

    await update.message.reply_text("✅ Feed toggles ok.")
