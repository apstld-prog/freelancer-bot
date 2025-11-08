# handlers_settings.py â€” FULL VERSION (no cuts)
import logging
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from db import get_session
from sqlalchemy import text

log = logging.getLogger(__name__)

# --- Settings Display ---
def build_settings_text(user_row) -> str:
    """Returns formatted settings text for a given user."""
    country = user_row.get("country_filter") or "ðŸŒ All countries"
    proposal = user_row.get("default_proposal") or "âœï¸ None set"
    expiry = user_row.get("license_until") or user_row.get("trial_end")
    expiry_text = expiry.strftime("%Y-%m-%d %H:%M UTC") if expiry else "N/A"

    return (
        "<b>âš™ï¸ Your Settings</b>\n\n"
        f"<b>ðŸŒŽ Country filter:</b> {country}\n"
        f"<b>ðŸ“„ Default proposal:</b>\n<code>{proposal}</code>\n\n"
        f"<b>ðŸ•’ License / Trial ends:</b> {expiry_text}\n\n"
        "You can update settings with:\n"
        "â€¢ <code>/setcountry US,UK</code>\n"
        "â€¢ <code>/setproposal &lt;text&gt;</code>\n"
        "â€¢ <code>/settings</code> (to view again)"
    )

# --- /settings Command ---
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows the userâ€™s settings (country, proposal, expiry)."""
    user = update.effective_user
    with get_session() as s:
        row = s.execute(
            text(
                """
                SELECT country_filter, default_proposal, license_until, trial_end
                FROM "user" WHERE telegram_id=:tid
                """
            ),
            {"tid": user.id},
        ).mappings().first()
    if not row:
        await update.message.reply_text("âš ï¸ You need to /start first.")
        return

    msg = build_settings_text(row)
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    log.info("âš™ï¸ Settings shown to user %s", user.id)

# --- /setcountry Command ---
async def setcountry_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Updates userâ€™s country filter."""
    if not context.args:
        await update.message.reply_text("Usage: /setcountry US,UK,GR")
        return
    countries = ", ".join(context.args)
    user = update.effective_user

    with get_session() as s:
        s.execute(
            text('UPDATE "user" SET country_filter=:c WHERE telegram_id=:tid'),
            {"c": countries, "tid": user.id},
        )
        s.commit()
    await update.message.reply_text(f"âœ… Country filter updated to: <b>{countries}</b>", parse_mode=ParseMode.HTML)
    log.info("ðŸŒ Country filter updated for user %s -> %s", user.id, countries)

# --- /setproposal Command ---
async def setproposal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sets userâ€™s default proposal text (used in auto proposals)."""
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("Usage: /setproposal &lt;your proposal text&gt;", parse_mode=ParseMode.HTML)
        return
    proposal = " ".join(context.args).strip()
    with get_session() as s:
        s.execute(
            text('UPDATE "user" SET default_proposal=:p WHERE telegram_id=:tid'),
            {"p": proposal, "tid": user.id},
        )
        s.commit()
    await update.message.reply_text("âœ… Default proposal saved successfully.")
    log.info("âœï¸ Proposal text updated for user %s", user.id)

# --- Register Settings Handlers ---
def register_settings_handlers(app):
    from telegram.ext import CommandHandler
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("setcountry", setcountry_command))
    app.add_handler(CommandHandler("setproposal", setproposal_command))

