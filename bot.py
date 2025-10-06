# bot.py
from __future__ import annotations
import os
import logging
from datetime import datetime, timezone, timedelta
from typing import List

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
)

# ====== logging ======
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

# ====== config ======
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = os.getenv("ADMIN_TELEGRAM_ID", "")  # single admin id as string

# ====== simple in-memory user store just for demo wiring (DB is in your other files) ======
# We only keep username cache here for /whoami output. Real data remains in your DB.
_USER_CACHE = {}

# ====== helpers ======
def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def is_admin(user_id: int) -> bool:
    return ADMIN_ID and str(user_id) == str(ADMIN_ID)

def main_menu_keyboard(is_admin_user: bool) -> InlineKeyboardMarkup:
    # 3 rows x 2 columns (as per your “good” screenshot)
    rows = [
        [
            InlineKeyboardButton("➕ Add Keywords", callback_data="mm:addkw"),
            InlineKeyboardButton("⚙️ Settings", callback_data="mm:settings"),
        ],
        [
            InlineKeyboardButton("📖 Help", callback_data="mm:help"),
            InlineKeyboardButton("💾 Saved", callback_data="mm:saved"),
        ],
        [
            InlineKeyboardButton("📨 Contact", callback_data="mm:contact"),
            InlineKeyboardButton("👑 Admin", callback_data="mm:admin") if is_admin_user
            else InlineKeyboardButton(" ", callback_data="mm:none"),
        ],
    ]
    # If not admin, drop the last placeholder cell to keep nice grid
    if not is_admin_user:
        rows[-1] = [InlineKeyboardButton("📨 Contact", callback_data="mm:contact")]
    return InlineKeyboardMarkup(rows)

WELCOME_TEXT_TOP = (
    "👋 *Welcome to Freelancer Alert Bot!*\n\n"
    "🎁 You have a *10-day free trial*.\n"
    "Automatically finds matching freelance jobs from top platforms and sends you instant alerts with affiliate-safe links.\n\n"
    "Use /help to see how it works."
)

FEATURES_BLOCK = (
    "✨ *Features*\n"
    "• Realtime job alerts (Freelancer API)\n"
    "• Affiliate-wrapped *Proposal* & *Original* links\n"
    "• Budget shown + USD conversion\n"
    "• ⭐ *Keep* / 🗑️ *Delete* buttons\n"
    "• 10-day free trial, extend via admin\n"
    "• Multi-keyword search (single/all modes)\n"
    "• Platforms by country (incl. GR boards)\n"
)

HELP_TEXT = (
    "🧭 *Help / How it works*\n\n"
    "1️⃣ Add keywords with `/addkeyword python, telegram` (comma-separated, English or Greek).\n"
    "2️⃣ Set your countries with `/setcountry US,UK` (or `ALL`).\n"
    "3️⃣ Save a proposal template with `/setproposal <text>`.\n"
    "   Placeholders: {jobtitle}, {experience}, {stack}, {availability}, {step1}, {step2}, {step3}, {budgettime}, {portfolio}, {name}\n"
    "4️⃣ When a job arrives you can:\n"
    "   ⭐ Keep it\n"
    "   🗑️ Delete it\n"
    "   📦 Proposal → direct affiliate link to job\n"
    "   🪪 Original → same affiliate-wrapped job link\n\n"
    "➤ Use `/mysettings` anytime to check your filters and proposal.\n"
    "➤ `/selftest` for a test job.\n"
    "➤ `/platforms CC` to see platforms by country (e.g., `/platforms GR`).\n\n"
    "📋 *Platforms monitored:*\n"
    "• Global: Freelancer.com (affiliate links), PeoplePerHour, Malt, Workana, Guru, 99designs, Toptal*, Codeable*, YunoJuno*, Worksome*, twago, freelancermap\n"
    "  (* referral/curated platforms)\n"
    "• Greece: JobFind.gr, Skywalker.gr, Kariera.gr\n\n"
    "👑 *Admin commands*\n"
    "/users — list users\n"
    "/grant <telegram_id> <days> — extend license\n"
    "/block <telegram_id> / /unblock <telegram_id>\n"
    "/broadcast <text> — send message to all active\n"
    "/feedsstatus — show active feed toggles\n"
)

# ====== /start ======
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    u = update.effective_user
    _USER_CACHE[u.id] = {"name": u.full_name or "", "username": u.username or ""}
    # main “card”
    await update.effective_message.reply_markdown(
        WELCOME_TEXT_TOP,
        reply_markup=main_menu_keyboard(is_admin(u.id)),
    )
    # features block (separate message, exactly as your “good” screenshot)
    await update.effective_message.reply_markdown(FEATURES_BLOCK)

# ====== unified button handler (we only open help/settings placeholders here) ======
async def menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    data = q.data or ""
    await q.answer()
    if data == "mm:help":
        await q.message.reply_markdown(HELP_TEXT)
    elif data == "mm:settings":
        # render a concise settings text (your full settings view lives elsewhere)
        await q.message.reply_markdown("🛠 *Your Settings*\n• Use `/mysettings` to view full details.")
    elif data == "mm:addkw":
        await q.message.reply_markdown("Use `/addkeyword` followed by comma-separated keywords.")
    elif data == "mm:saved":
        await q.message.reply_markdown("Opening your saved jobs… Use `/saved` if you prefer.")
    elif data == "mm:contact":
        await q.message.reply_markdown("✍️ Please type your message for the admin. I’ll forward it right away.")
    elif data == "mm:admin":
        if is_admin(update.effective_user.id):
            await q.message.reply_markdown("👑 Admin panel — use the admin commands listed in /help.")
        else:
            await q.message.reply_text("Admin only.")
    else:
        await q.message.reply_text("…")

# ====== simple commands kept (placeholders that you already have elsewhere) ======
async def selftest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("✅ Bot is active and responding normally!")

async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    u = update.effective_user
    cached = _USER_CACHE.get(u.id, {})
    username = cached.get("username") or u.username or "(none)"
    await update.message.reply_text(f"🔗 Username: {username}")

# ====== feedsstatus wiring (admin-only handler lives in separate file) ======
from feedsstatus_handler import register_feedsstatus_handler

# ====== build app ======
def build_application() -> Application:
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CallbackQueryHandler(menu_cb, pattern=r"^mm:"))
    app.add_handler(CommandHandler("selftest", selftest_cmd))
    app.add_handler(CommandHandler("whoami", whoami_cmd))
    # admin: /feedsstatus
    register_feedsstatus_handler(app)
    return app

# ====== webhook entry for server.py ======
tg_app: Application = build_application()

if __name__ == "__main__":
    # For local polling runs
    ApplicationBuilder().token(BOT_TOKEN).build()
