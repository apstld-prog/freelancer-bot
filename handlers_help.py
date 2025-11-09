import logging
from telegram import Update
from telegram.ext import ContextTypes
from config import ADMIN_IDS

log = logging.getLogger("handlers_help")


HELP_TEXT = (
    "🩵 *Help / How it works*\n"
    "1️⃣ Add keywords with /addkeyword python, telegram (comma-separated, English or Greek).\n"
    "2️⃣ Set your countries with /setcountry US,UK (or ALL).\n"
    "3️⃣ Save a proposal template with /setproposal <text>.\n"
    "   Placeholders: {jobtitle}, {experience}, {stack}, {availability}, {step1}, "
    "{step2}, {step3}, {budgettime}, {portfolio}, {name}\n"
    "4️⃣ When a job arrives you can:\n"
    "   ⭐ Keep it\n"
    "   🗑️ Delete it\n"
    "   📩 Proposal → direct affiliate link to job\n"
    "   🌐 Original → same affiliate-wrapped job link\n"
    "➡️ Use /mysettings anytime to check your filters and proposal.\n"
    "➡️ /selftest for a test job.\n"
    "➡️ /platforms CC to see platforms by country (e.g. /platforms GR).\n"
    "________________________________________\n"
    "🌍 *Platforms monitored:*\n"
    "Global: Freelancer.com (affiliate links), PeoplePerHour, Malt, Workana, Guru, "
    "99designs, Toptal*, Codeable*, YunoJuno*, Worksome*, twago, freelancermap\n"
    "(*referral/curated platforms)\n"
    "Greece: JobFind.gr, Skywalker.gr, Kariera.gr\n"
)


ADMIN_TEXT = (
    "👑 *Admin commands*\n"
    "• /users – list users\n"
    "• /grant <telegram_id> <days> – extend license\n"
    "• /block <telegram_id> / unblock <telegram_id>\n"
    "• /broadcast <text> – send message to all active\n"
    "• /feedsstatus – show active feed toggles\n"
    "/SELFTEST\n"
    "/WORKERS_TEST"
)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Standard /help command."""
    uid = update.effective_user.id
    text = HELP_TEXT

    if uid in ADMIN_IDS:
        text += "\n________________________________________\n" + ADMIN_TEXT

    await update.message.reply_text(text, parse_mode="Markdown")


async def admin_help_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Triggered when user presses Help button in UI."""
    query = update.callback_query
    await query.answer()

    uid = query.from_user.id
    text = HELP_TEXT

    if uid in ADMIN_IDS:
        text += "\n________________________________________\n" + ADMIN_TEXT

    await query.edit_message_text(text, parse_mode="Markdown")

