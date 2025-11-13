from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler
from utils import get_user, create_user_if_missing


START_TEXT = (
    "👋 Welcome to Freelancer Alert Bot!\n"
    "🎁 You have a 10-day free trial.\n"
    "Automatically finds matching freelance jobs from top platforms and sends you instant alerts with affiliate-safe links.\n"
    "Use /help to see how it works.\n"
    "________________________________________\n"
    "🟩 Keywords  ⚙️ Settings\n"
    "📘 Help  💾 Saved\n"
    "📞 Contact\n"
    "🔥 Admin\n"
    "________________________________________\n"
    "✨ Features\n"
    "• Realtime job alerts (Freelancer API)\n"
    "• Affiliate-wrapped Proposal & Original links\n"
    "• Budget shown + USD conversion\n"
    "• ⭐ Keep / 🗑️ Delete buttons\n"
    "• 10-day free trial, extend via admin\n"
    "• Multi-keyword search (single/all modes)\n"
    "• Platforms by country (incl. GR boards)"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id

    # ensure user exists
    user = get_user(tid)
    if not user:
        create_user_if_missing(tid)

    keyboard = [
        [
            InlineKeyboardButton("🟩 Keywords", callback_data="keywords"),
            InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
        ],
        [
            InlineKeyboardButton("📘 Help", callback_data="help"),
            InlineKeyboardButton("💾 Saved", callback_data="saved"),
        ],
        [InlineKeyboardButton("📞 Contact", callback_data="contact")],
        [InlineKeyboardButton("🔥 Admin", callback_data="admin")],
    ]

    await update.message.reply_text(
        START_TEXT,
        reply_markup=InlineKeyboardMarkup(keyboard),
        disable_web_page_preview=True,
    )


def register_start_handlers(app):
    app.add_handler(CommandHandler("start", start))
