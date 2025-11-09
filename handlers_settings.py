import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from utils import get_user, set_user_setting
from db_keywords import get_keywords
from config import ADMIN_IDS

log = logging.getLogger("handlers_settings")


async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    uid = query.from_user.id
    user = get_user(uid)
    if not user:
        await query.edit_message_text("User not found.")
        return

    keywords = ", ".join(get_keywords(uid)) or "(none)"
    countries = user["countries"] or "ALL"
    proposal = user["proposal_template"] or "(none)"

    text = (
        "ðŸ›  *Your Settings*\n"
        f"â€¢ Keywords: {keywords}\n"
        f"â€¢ Countries: {countries}\n"
        f"â€¢ Proposal template: {proposal}\n\n"
        "ðŸŸ¢ Start date: â€”\n"
        f"ðŸŸ¢ Trial ends: â€”\n"
        f"ðŸŸ¢ License until: None\n"
        f"âœ… Active: { 'âœ…' if user['active'] else 'âŒ' }\n"
        f"ðŸš« Blocked: { 'âœ…' if user['blocked'] else 'âŒ' }\n"
        "________________________________________\n"
        "ðŸŒ Platforms monitored:\n"
        "Global: Freelancer.com (affiliate links), PeoplePerHour, Malt, Workana, Guru, "
        "99designs, Toptal*, Codeable*, YunoJuno*, Worksome*, twago, freelancermap\n"
        "(*referral/curated platforms)\n"
        "Greece: JobFind.gr, Skywalker.gr, Kariera.gr\n"
        "________________________________________\n"
        "For extension, contact the admin."
    )

    kb = [[InlineKeyboardButton("Back", callback_data="ui:main")]]

    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


