import logging
from telegram import Update
from telegram.ext import ContextTypes
from config import ADMIN_IDS

log = logging.getLogger("handlers_help")


HELP_TEXT = (
    "ðŸ©µ *Help / How it works*\n"
    "1ï¸âƒ£ Add keywords with /addkeyword python, telegram (comma-separated, English or Greek).\n"
    "2ï¸âƒ£ Set your countries with /setcountry US,UK (or ALL).\n"
    "3ï¸âƒ£ Save a proposal template with /setproposal <text>.\n"
    "   Placeholders: {jobtitle}, {experience}, {stack}, {availability}, {step1}, "
    "{step2}, {step3}, {budgettime}, {portfolio}, {name}\n"
    "4ï¸âƒ£ When a job arrives you can:\n"
    "   â­ Keep it\n"
    "   ðŸ—‘ï¸ Delete it\n"
    "   ðŸ“© Proposal â†’ direct affiliate link to job\n"
    "   ðŸŒ Original â†’ same affiliate-wrapped job link\n"
    "âž¡ï¸ Use /mysettings anytime to check your filters and proposal.\n"
    "âž¡ï¸ /selftest for a test job.\n"
    "âž¡ï¸ /platforms CC to see platforms by country (e.g. /platforms GR).\n"
    "________________________________________\n"
    "ðŸŒ *Platforms monitored:*\n"
    "Global: Freelancer.com (affiliate links), PeoplePerHour, Malt, Workana, Guru, "
    "99designs, Toptal*, Codeable*, YunoJuno*, Worksome*, twago, freelancermap\n"
    "(*referral/curated platforms)\n"
    "Greece: JobFind.gr, Skywalker.gr, Kariera.gr\n"
)


ADMIN_TEXT = (
    "ðŸ‘‘ *Admin commands*\n"
    "â€¢ /users â€“ list users\n"
    "â€¢ /grant <telegram_id> <days> â€“ extend license\n"
    "â€¢ /block <telegram_id> / unblock <telegram_id>\n"
    "â€¢ /broadcast <text> â€“ send message to all active\n"
    "â€¢ /feedsstatus â€“ show active feed toggles\n"
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


