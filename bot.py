import os
import logging
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from sqlalchemy import text as _t

# Project helpers
from db import get_session, get_or_create_user_by_tid
from ui_texts import welcome_full, help_footer

# ==========================================================
# Logging
# ==========================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==========================================================
# Main keyboard (fallback – ίδιο layout με screenshots)
# ==========================================================
def main_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("+ Add Keywords", callback_data="act:addkw"),
                InlineKeyboardButton("⚙️ Settings", callback_data="act:settings"),
            ],
            [
                InlineKeyboardButton("🆘 Help", callback_data="act:help"),
                InlineKeyboardButton("💾 Saved", callback_data="act:saved"),
            ],
            [
                InlineKeyboardButton("📨 Contact", callback_data="act:contact"),
                InlineKeyboardButton("🔥 Admin", callback_data="act:admin"),
            ],
        ]
    )

# ==========================================================
# Admin check (προσαρμόζεται στα δικά σου ids στο .env)
# ==========================================================
def is_admin_user(tid: int) -> bool:
    admins = [x.strip() for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
    return str(tid) in admins

# ==========================================================
# /start — initialize & show trial dates
# ==========================================================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    days = int(os.getenv("TRIAL_DAYS", "10"))

    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)

        # Initialize missing dates
        s.execute(
            _t('UPDATE "user" SET trial_start = COALESCE(trial_start, NOW()) WHERE id=:id'),
            {"id": u.id},
        )
        s.execute(
            _t(
                'UPDATE "user" '
                "SET trial_end = COALESCE(trial_end, NOW() + (:d || ' days')::interval) "
                "WHERE id=:id"
            ),
            {"id": u.id, "d": str(days)},
        )
        s.commit()

        row = s.execute(
            _t(
                'SELECT trial_start, trial_end, license_until '
                'FROM "user" WHERE id=:id'
            ),
            {"id": u.id},
        ).fetchone()

    # Welcome + κύριο μενού
    await update.effective_chat.send_message(
        welcome_full(days),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=main_keyboard(is_admin_user(update.effective_user.id)),
    )

    # Μπλοκ με ημερομηνίες
    if row:
        ts, te, lic = row
        await update.effective_chat.send_message(
            f"<b>🧾 Your access</b>\n• Start: {ts}\n• Trial ends: {te} UTC\n• License until: {lic}",
            parse_mode=ParseMode.HTML,
        )

# ==========================================================
# /help — κρύβει admin block από μη-admin
# ==========================================================
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    is_admin = is_admin_user(uid)
    text = (
        "Welcome to Freelancer Alert Bot!\n\n"
        "Use the menu below to manage your alerts and settings."
        + help_footer(24, admin=is_admin)
    )
    await update.effective_chat.send_message(text, parse_mode=ParseMode.HTML)

# ==========================================================
# Callback handler για ΟΛΑ τα κουμπιά
# ==========================================================
async def cb_mainmenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    data = q.data or ""
    await q.answer()

    # Βασικές ενέργειες με ίδιο στήσιμο
    if data == "act:addkw":
        await q.message.reply_text("Send: /addkeyword word1, word2")
    elif data == "act:settings":
        # Αν έχεις δικό σου /mysettings, κάλεσέ το – εδώ στέλνουμε απλό hint
        await q.message.reply_text("Open /mysettings to view your settings.")
    elif data == "act:help":
        await help_cmd(update, context)
    elif data == "act:saved":
        # Αν έχεις δικό σου /saved, μπορείς να το καλέσεις. Εδώ απλά hint.
        await q.message.reply_text("Open /saved to view your saved jobs.")
    elif data == "act:contact":
        handle = os.getenv("CONTACT_HANDLE", "@your_username")
        await q.message.reply_text(f"Contact: {handle}", disable_web_page_preview=True)
    elif data == "act:admin":
        if is_admin_user(update.effective_user.id):
            await q.message.reply_text(
                "/users, /grant <id> <days>, /block <id>, /unblock <id>, /broadcast <text>, /feedstatus"
            )
        else:
            await q.message.reply_text("You're not an admin.")
    elif data.startswith("job:"):
        # Ελάχιστη συμπεριφορά Save/Delete (χωρίς να αλλάξουμε το UI)
        if data == "job:save":
            try:
                await q.message.delete()
            except Exception:
                pass
            await q.message.chat.send_message("⭐ Saved to your list.")
        elif data == "job:delete":
            try:
                await q.message.delete()
            except Exception:
                pass
            await q.message.chat.send_message("🗑️ Deleted.")
        else:
            await q.message.chat.send_message("Unknown action.")
    else:
        await q.message.reply_text("Unknown action.")

# ==========================================================
# Application builder
# ==========================================================
def build_application() -> Application:
    token = os.getenv("BOT_TOKEN")
    app = ApplicationBuilder().token(token).build()

    # Commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))

    # Callback query handler for all inline buttons
    app.add_handler(CallbackQueryHandler(cb_mainmenu))

    logger.info("✅ Application handlers registered.")
    return app

# ==========================================================
# Standalone run (optional)
# ==========================================================
if __name__ == "__main__":
    app = build_application()
    app.run_polling()
