# handlers_help.py â€” FULL VERSION (no cuts)
import logging
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from config import STATS_WINDOW_HOURS
from db_events import get_platform_stats

log = logging.getLogger(__name__)

HELP_TEXT = (
    "<b>ðŸ§­ Help / How it works</b>\n\n"
    "<b>1ï¸âƒ£ Add your keywords</b>\n"
    "Use <code>/addkeyword logo, lighting, website</code> â€” youâ€™ll only get alerts matching these terms.\n\n"
    "<b>2ï¸âƒ£ Manage keywords</b>\n"
    "â€¢ View your list: <code>/listkeywords</code>\n"
    "â€¢ Remove: <code>/delkeyword logo</code>\n"
    "â€¢ Clear all: <code>/clearkeywords</code>\n\n"
    "<b>3ï¸âƒ£ Platforms</b>\n"
    "The bot monitors multiple global and EU freelance boards â€” real-time scanning every minute.\n\n"
    "<b>4ï¸âƒ£ Alerts</b>\n"
    "Youâ€™ll receive instant alerts when job titles or descriptions contain your keywords.\n"
    "Each alert shows the title, budget, currency (converted to USD), platform source, and posting time.\n\n"
    "<b>5ï¸âƒ£ Saved Jobs</b>\n"
    "Tap â­ Save on any alert to keep it in your saved list.\n\n"
    "<b>6ï¸âƒ£ Contact</b>\n"
    "ðŸ“¨ Support: <a href='https://t.me/freelancer_alert_support'>@freelancer_alert_support</a>\n"
)

def help_footer(hours: int) -> str:
    return (
        "\n<b>ðŸ›° Platforms monitored:</b>\n"
        "â€¢ Freelancer, PeoplePerHour, Malt, Workana, Guru, 99designs,\n"
        "  Toptal*, Codeable*, YunoJuno*, Worksome*, twago, freelancermap\n"
        "â€¢ Greek boards: Skywalker, Kariera, JobFind\n\n"
        f"<i>Stats window: last {hours}h</i>"
    )

# --- /help Command Handler ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows main help content."""
    try:
        msg = HELP_TEXT + help_footer(STATS_WINDOW_HOURS)
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        log.info("âœ… Sent /help to user %s", update.effective_user.id)
    except Exception as e:
        log.error("âŒ Error in help_command: %s", e)
        await update.message.reply_text("âš ï¸ An error occurred while showing help.")

# --- Feed status helper for /help menu ---
async def feed_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays feed statistics for platforms."""
    try:
        stats = get_platform_stats(hours=STATS_WINDOW_HOURS)
        msg = "<b>ðŸ“Š Feed Status</b>\n"
        if not stats:
            msg += "No recent feed activity."
        else:
            for p, c in stats.items():
                msg += f"â€¢ {p.title()}: {c} jobs in the last {STATS_WINDOW_HOURS}h\n"
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        log.info("ðŸ“ˆ Feed stats sent to user %s", update.effective_user.id)
    except Exception as e:
        log.error("Error in feed_status: %s", e)
        await update.message.reply_text("âš ï¸ Failed to retrieve feed stats.")

# --- Register handlers (for integration in bot.py) ---
def register_help_handlers(app):
    from telegram.ext import CommandHandler
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("feedstatus", feed_status))



