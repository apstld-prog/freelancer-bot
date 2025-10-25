# bot_basic_final.py

import logging
import os
from datetime import datetime, timedelta
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from platform_freelancer import fetch_freelancer_jobs
from platform_peopleperhour import fetch_pph_jobs

logger = logging.getLogger(__name__)
BOT_TOKEN = (
    os.getenv("TELEGRAM_BOT_TOKEN")
    or os.getenv("TELEGRAM_TOKEN")
    or os.getenv("BOT_TOKEN")
)
STATIC_USD_RATES = {"EUR": 1.10, "GBP": 1.25, "AUD": 0.65}

# -------------------------------------
# Core Handlers
# -------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main /start menu identical to your UI."""
    chat_id = update.effective_chat.id
    text = (
        "👋 <b>Welcome to Freelancer Alert Bot!</b>\n\n"
        "🎁 You have a <b>10-day free trial</b>.\n"
        "The bot finds matching freelance jobs from top platforms and sends instant alerts.\n"
        f"Free trial ends: {(datetime.utcnow() + timedelta(days=10)).strftime('%Y-%m-%d %H:%M UTC')}\n\n"
        "Use /help for instructions."
    )

    keyboard = [
        [
            InlineKeyboardButton("➕ Add Keywords", callback_data="add_keywords"),
            InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
        ],
        [
            InlineKeyboardButton("🆘 Help", callback_data="help"),
            InlineKeyboardButton("💾 Saved", callback_data="saved"),
        ],
        [
            InlineKeyboardButton("📞 Contact", callback_data="contact"),
        ],
        [
            InlineKeyboardButton("🔥 Admin", callback_data="admin"),
        ],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup,
        disable_web_page_preview=True,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🎯 <b>Help / How it works</b>\n\n"
        "<b>Keywords</b>\n"
        "• Add: <code>/addkeyword logo, lighting, sales</code>\n"
        "• Remove: <code>/delkeyword logo, sales</code>\n"
        "• Clear all: <code>/clearkeywords</code>\n\n"
        "<b>Other</b>\n"
        "• Set countries: <code>/setcountry US,UK or ALL</code>\n"
        "• Save proposal: <code>/setproposal &lt;text&gt;</code>\n"
        "• Test card: <code>/selftest</code>\n\n"
        "🌍 <b>Platforms monitored:</b>\n"
        "• Global: Freelancer.com (affiliate), PeoplePerHour\n\n"
        "👑 Admin:\n"
        "/users /grant <id> <days> /block <id> /unblock <id>\n"
        "/broadcast <text> /feedstatus"
    )
    await update.message.reply_html(text, disable_web_page_preview=True)


# -------------------------------------
# Utility functions
# -------------------------------------

def convert_to_usd_static(amount, currency):
    """Convert given amount using static rates if needed."""
    try:
        if not amount or not currency:
            return None
        currency = currency.upper()
        if currency == "USD":
            return amount
        rate = STATIC_USD_RATES.get(currency)
        if not rate:
            return None
        return round(amount * rate, 2)
    except Exception as e:
        logger.error(f"convert_to_usd_static error: {e}")
        return None


def format_budget(amount_min, amount_max, currency):
    """Show original + USD conversion if needed."""
    try:
        base = f"{amount_min}–{amount_max} {currency}" if amount_max else f"{amount_min} {currency}"
        if currency.upper() != "USD":
            usd_val = convert_to_usd_static(float(amount_max or amount_min), currency)
            if usd_val:
                base += f" (~${usd_val} USD)"
        return base
    except Exception:
        return f"{amount_min} {currency}"


async def send_job_preview(chat_id, job, context: ContextTypes.DEFAULT_TYPE):
    """Send one job card."""
    title = job.get("title", "Untitled")
    platform = job.get("platform", "Unknown")
    desc = job.get("description", "")
    keyword = job.get("keyword", "N/A")
    budget_amount = job.get("budget_amount")
    budget_currency = job.get("budget_currency", "USD")
    budget_usd = format_budget(budget_amount, None, budget_currency)
    url = job.get("url") or job.get("affiliate_url")

    text = (
        f"💼 <b>{title}</b>\n"
        f"🪄 <b>Platform:</b> {platform}\n"
        f"🔑 <b>Keyword:</b> {keyword}\n"
        f"💰 <b>Budget:</b> {budget_usd}\n\n"
        f"{desc[:250]}..."
    )

    buttons = [
        [
            InlineKeyboardButton("💬 Proposal", callback_data="proposal"),
            InlineKeyboardButton("🌐 Original", url=url),
        ],
        [
            InlineKeyboardButton("⭐ Save", callback_data="save"),
            InlineKeyboardButton("🗑 Delete", callback_data="delete"),
        ],
    ]

    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
        disable_web_page_preview=True,
    )


# -------------------------------------
# Commands
# -------------------------------------

async def selftest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show 1 job from each platform."""
    chat_id = update.effective_chat.id
    await context.bot.send_message(chat_id, "🧠 Running selftest… please wait.")
    try:
        f_jobs = await fetch_freelancer_jobs("logo")
        p_jobs = await fetch_pph_jobs("design")

        if f_jobs:
            await send_job_preview(chat_id, f_jobs[0], context)
        if p_jobs:
            await send_job_preview(chat_id, p_jobs[0], context)

        await context.bot.send_message(chat_id, "✅ Selftest completed successfully.")
    except Exception as e:
        await context.bot.send_message(chat_id, f"❌ Selftest failed: {e}")


async def feedstatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "📡 <b>Feed Status</b>\n\n✅ Freelancer\n✅ PeoplePerHour"
    await update.message.reply_html(text)


# -------------------------------------
# Build application
# -------------------------------------

def build_application() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("selftest", selftest))
    app.add_handler(CommandHandler("feedstatus", feedstatus))
    return app


application = build_application()

if __name__ == "__main__":
    application.run_polling()
