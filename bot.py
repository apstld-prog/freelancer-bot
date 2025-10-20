import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
)
from datetime import datetime
from utils import (
    load_users,
    save_users,
    format_jobs,
    load_keywords,
    is_admin,
)
from config import BOT_TOKEN

# -----------------------------------------------------
# Logging setup
# -----------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# -----------------------------------------------------
# Load data
# -----------------------------------------------------
USERS = load_users()
KEYWORDS = load_keywords()

# -----------------------------------------------------
# Telegram bot functions
# -----------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or "Χρήστης"

    if user_id not in USERS:
        USERS[user_id] = {"name": user_name, "joined": datetime.now().isoformat()}
        save_users(USERS)

    await update.message.reply_text(
        f"👋 Καλώς ήρθες, {user_name}!\n"
        f"Παρακολουθώ νέες αγγελίες σε Freelancer & PeoplePerHour.\n"
        f"Θα ενημερωθείς αυτόματα όταν εμφανιστούν σχετικές αγγελίες!"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛠 Διαθέσιμες εντολές:\n"
        "/start - Επανεκκίνηση bot\n"
        "/help - Λίστα εντολών\n"
        "/keywords - Προβολή λέξεων-κλειδιών"
    )

async def show_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not KEYWORDS:
        await update.message.reply_text("⚠ Δεν υπάρχουν λέξεις-κλειδιά αυτή τη στιγμή.")
        return

    formatted = "\n".join([f"• {kw}" for kw in KEYWORDS])
    await update.message.reply_text(f"📋 Τρέχουσες λέξεις-κλειδιά:\n{formatted}")

async def send_job_alert(context: ContextTypes.DEFAULT_TYPE, job):
    chat_id = context.job.chat_id
    message = format_jobs([job])
    await context.bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML")

# -----------------------------------------------------
# Inline keyboard example
# -----------------------------------------------------
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 Δεν έχεις πρόσβαση στο admin panel.")
        return

    keyboard = [
        [InlineKeyboardButton("📊 Προβολή Χρηστών", callback_data="show_users")],
        [InlineKeyboardButton("⚙️ Ρυθμίσεις", callback_data="settings")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🔧 Επιλογές διαχείρισης:", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "show_users":
        users_list = "\n".join(
            [f"{uid}: {data['name']}" for uid, data in USERS.items()]
        )
        await query.edit_message_text(text=f"👥 Εγγεγραμμένοι χρήστες:\n{users_list}")
    elif query.data == "settings":
        await query.edit_message_text(text="⚙️ Δεν υπάρχουν διαθέσιμες ρυθμίσεις ακόμα.")

# -----------------------------------------------------
# Build and start bot
# -----------------------------------------------------
def build_application():
    if not BOT_TOKEN:
        raise ValueError("❌ BOT_TOKEN is missing. Check environment or config.py.")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("keywords", show_keywords))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(button_handler))

    return app

if __name__ == "__main__":
    app = build_application()
    print("✅ Bot starting...")
    app.run_polling()
