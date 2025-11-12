
import os, logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, Application, CommandHandler, CallbackQueryHandler, ContextTypes
from config import ADMIN_IDS, TRIAL_DAYS

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

WELCOME_TEXT = """👋 Welcome to Freelancer Alert Bot!
🎁 You have a 10-day free trial.
Automatically finds matching freelance jobs from top platforms and sends you instant alerts with affiliate-safe links.
Use /help to see how it works.
________________________________________
🟩 Keywords  ⚙️ Settings
📘 Help  💾 Saved
📞 Contact
🔥 Admin
________________________________________
✨ Features
• Realtime job alerts (Freelancer API)
• Affiliate-wrapped Proposal & Original links
• Budget shown + USD conversion
• ⭐ Keep / 🗑️ Delete buttons
• 10-day free trial, extend via admin
• Multi-keyword search (single/all modes)
• Platforms by country (incl. GR boards)"""

HELP_TEXT = """🩵 Help / How it works
1️⃣ Add keywords with /addkeyword python, telegram (comma-separated, English or Greek).
2️⃣ Set your countries with /setcountry US,UK (or ALL).
3️⃣ Save a proposal template with /setproposal <text>.
   Placeholders: {{jobtitle}}, {{experience}}, {{stack}}, {{availability}}, {{step1}}, {{step2}}, {{step3}}, {{budgettime}}, {{portfolio}}, {{name}}
4️⃣ When a job arrives you can:
   ⭐ Keep it
   🗑️ Delete it
   📩 Proposal → direct affiliate link to job
   🌐 Original → same affiliate-wrapped job link
➡️ Use /mysettings anytime to check your filters and proposal.
➡️ /selftest for a test job.
➡️ /platforms CC to see platforms by country (e.g. /platforms GR).
________________________________________
🌍 Platforms monitored:
Global: Freelancer.com (affiliate links), PeoplePerHour, Malt, Workana, Guru, 99designs, Toptal*, Codeable*, YunoJuno*, Worksome*, twago, freelancermap
(*referral/curated platforms)
Greece: JobFind.gr, Skywalker.gr, Kariera.gr"""

def main_keyboard(is_admin: bool):
    rows = [
        [InlineKeyboardButton("🟩 Keywords", callback_data="kw"), InlineKeyboardButton("⚙️ Settings", callback_data="settings")],
        [InlineKeyboardButton("📘 Help", callback_data="help"), InlineKeyboardButton("💾 Saved", callback_data="saved")],
        [InlineKeyboardButton("📞 Contact", callback_data="contact")]
    ]
    if is_admin:
        rows.append([InlineKeyboardButton("🔥 Admin", callback_data="admin")])
    return InlineKeyboardMarkup(rows)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_admin = False
    try:
        tid = user.id if user else 0
        if isinstance(ADMIN_IDS, (set, list, tuple)):
            is_admin = str(tid) in set(map(str, ADMIN_IDS))
        else:
            is_admin = False
    except Exception:
        pass
    await update.effective_message.reply_text(WELCOME_TEXT, reply_markup=main_keyboard(is_admin))

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(HELP_TEXT)

async def button_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    data = q.data or ""
    await q.answer()
    if data == "help":
        await q.edit_message_text(HELP_TEXT)
    elif data == "settings":
        await q.edit_message_text("🛠 Your Settings\n• Keywords: (set with /addkeyword)\n• Countries: ALL (default)\n• Proposal template: (none)\n🟢 Trial ends: auto\n🟢 License until: (admin-managed)\n✅ Active: ☑️\n🚫 Blocked: ☐\n________________________________________\nFor extension, contact the admin.")
    elif data == "kw":
        await q.edit_message_text("Use /addkeyword to add keywords, comma-separated. Example: /addkeyword logo, lighting, luminaire")
    elif data == "saved":
        await q.edit_message_text("No saved items yet. ⭐ Keep a job to save it.")
    elif data == "contact":
        await q.edit_message_text("📩 Send your message here. The admin will reply to you.")
    elif data == "admin":
        await q.edit_message_text("👑 Admin commands\n• /users – list users\n• /grant <telegram_id> <days>\n• /block <telegram_id> / unblock <telegram_id>\n• /broadcast <text>\n• /feedsstatus\n• /selftest\n• /workers_test")
    else:
        await q.edit_message_text("Unknown action.")

def build_application() -> Application:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(button_router))
    return app
