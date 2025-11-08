# ==============================================================
# bot.py â€” FINAL FULL VERSION (Nov 2025)
# ==============================================================

import os
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
from sqlalchemy import text

from db import ensure_schema, get_session, get_or_create_user_by_tid
from config import ADMIN_IDS
from db_events import ensure_feed_events_schema
from handlers_ui import handle_ui_callback, handle_user_message

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("âŒ Missing TELEGRAM_BOT_TOKEN")


def main_menu(is_admin=False):
    rows = [
        [
            InlineKeyboardButton("âž• Add Keywords", callback_data="ui:addkw"),
            InlineKeyboardButton("âš™ Settings", callback_data="ui:settings")
        ],
        [
            InlineKeyboardButton("ðŸ’¾ Saved Jobs", callback_data="ui:saved"),
            InlineKeyboardButton("ðŸ“Š Feed Status", callback_data="ui:feed")
        ],
        [
            InlineKeyboardButton("ðŸ“¨ Contact", callback_data="ui:contact"),
            InlineKeyboardButton("ðŸ†˜ Help", callback_data="ui:help")
        ]
    ]
    if is_admin:
        rows.append([InlineKeyboardButton("ðŸ‘‘ Admin Panel", callback_data="ui:admin")])
    return InlineKeyboardMarkup(rows)


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    with get_session() as s:
        u = get_or_create_user_by_tid(s, uid)

        s.execute(text("""
            UPDATE "user"
            SET trial_start = COALESCE(trial_start, NOW()),
                trial_end   = COALESCE(trial_end, NOW() + INTERVAL '10 days')
            WHERE id=:i
        """), {"i": u.id})

        expiry = s.execute(
            text('SELECT trial_end FROM "user" WHERE id=:i'),
            {"i": u.id}
        ).scalar()

        if expiry is None:
            expiry = s.execute(
                text("""
                    UPDATE "user"
                    SET trial_end = NOW() + INTERVAL '10 days'
                    WHERE id=:i
                    RETURNING trial_end
                """),
                {"i": u.id}
            ).scalar()

        s.commit()

    expiry_str = expiry.strftime('%Y-%m-%d %H:%M UTC')

    txt = (
        "<b>ðŸ‘‹ Welcome to Freelancer Alert Bot!</b>\n\n"
        "ðŸŽ <b>Your 10-day free trial is active.</b>\n"
        "You will get real-time job alerts for your keywords.\n\n"
        f"<b>â³ Trial ends:</b> {expiry_str}\n"
        "____________________________________________"
    )
    await update.message.reply_text(
        txt,
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu(uid in ADMIN_IDS)
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ðŸ†˜ <b>Help</b>\nManage keywords, saved jobs and settings from the menu.",
        parse_mode=ParseMode.HTML
    )


def build_application():
    ensure_schema()
    ensure_feed_events_schema()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(handle_ui_callback, pattern=r"^ui:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))

    return app


async def on_startup():
    log.info("âœ… Telegram bot startup")


async def on_shutdown():
    log.info("ðŸ›‘ Telegram bot shutdown")

