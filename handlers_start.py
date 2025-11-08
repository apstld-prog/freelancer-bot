import logging
from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from db import get_session, get_or_create_user_by_tid
from config import TRIAL_DAYS
from utils import is_admin_user

log = logging.getLogger(__name__)


def main_menu_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("ðŸŸ© Add Keywords", callback_data="act:addkw"),
            InlineKeyboardButton("âš™ï¸ Settings", callback_data="act:settings"),
        ],
        [
            InlineKeyboardButton("ðŸ“˜ Help", callback_data="act:help"),
            InlineKeyboardButton("ðŸ’¾ Saved", callback_data="act:saved"),
        ],
        [
            InlineKeyboardButton("ðŸ“ž Contact", callback_data="act:contact"),
        ]
    ]
    if is_admin:
        rows.append([InlineKeyboardButton("ðŸ”¥ Admin", callback_data="act:admin")])
    return InlineKeyboardMarkup(rows)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    with get_session() as s:
        u = get_or_create_user_by_tid(s, user.id)

        # Trial calculation
        now = datetime.now(timezone.utc)

        if u.trial_start is None:
            u.trial_start = now
            u.trial_end = now + timedelta(days=TRIAL_DAYS)
            s.commit()

        trial_end_str = u.trial_end.strftime("%Y-%m-%d %H:%M UTC")

    text = (
        "ðŸ‘‹ <b>Welcome to Freelancer Alert Bot!</b>\n\n"
        "ðŸŽ <b>You have a 10-day free trial.</b>\n"
        "Automatically finds matching freelance jobs from top platforms and sends you instant alerts with affiliate-safe links.\n"
        "Use /help to see how it works.\n"
        "________________________________________\n"
        "ðŸŸ© <b>Keywords</b>â€ƒâ€ƒâš™ï¸ <b>Settings</b>\n"
        "ðŸ“˜ <b>Help</b>â€ƒâ€ƒðŸ’¾ <b>Saved</b>\n"
        "ðŸ“ž <b>Contact</b>\n"
        "ðŸ”¥ <b>Admin</b>\n"
        "________________________________________\n"
        "âœ¨ <b>Features</b>\n"
        "â€¢ Realtime job alerts (Freelancer API)\n"
        "â€¢ Affiliate-wrapped Proposal & Original links\n"
        "â€¢ Budget shown + USD conversion\n"
        "â€¢ â­ Keep / ðŸ—‘ï¸ Delete buttons\n"
        "â€¢ 10-day free trial, extend via admin\n"
        "â€¢ Multi-keyword search (single/all modes)\n"
        "â€¢ Platforms by country (incl. GR boards)\n"
        f"________________________________________\n"
        f"â³ <b>Trial ends:</b> {trial_end_str}"
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(
            is_admin=is_admin_user(user.id)
        ),
    )

    log.info("âœ… /start executed for user %s", user.id)



# auto-wiring for /start
from telegram.ext import CommandHandler
def setup(app):
    app.add_handler(CommandHandler("start", start_command))

