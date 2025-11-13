# handlers_help.py

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

HELP_TEXT = (
    "🩵 Help / How it works\n"
    "1️⃣ Add keywords with /addkeyword python, telegram (comma-separated, English or Greek).\n"
    "2️⃣ Set your countries with /setcountry US,UK (or ALL).\n"
    "3️⃣ Save a proposal template with /setproposal <text>.\n"
    "   Placeholders: {jobtitle}, {experience}, {stack}, {availability}, {step1}, {step2}, {step3}, {budgettime}, {portfolio}, {name}\n"
    "4️⃣ When a job arrives you can:\n"
    "   ⭐ Keep it\n"
    "   🗑️ Delete it\n"
    "   📩 Proposal → direct affiliate link to job\n"
    "   🌐 Original → same affiliate-wrapped job link\n"
    "➡️ Use /mysettings anytime to check your filters and proposal.\n"
    "➡️ /selftest for a test job.\n"
    "➡️ /platforms CC to see platforms by country (e.g. /platforms GR).\n"
    "________________________________________\n"
    "🌍 Platforms monitored:\n"
    "Global: Freelancer.com (affiliate links), PeoplePerHour, Malt, Workana, Guru, 99designs, Toptal*, Codeable*, YunoJuno*, Worksome*, twago, freelancermap\n"
    "(*referral/curated platforms)\n"
    "Greece: JobFind.gr, Skywalker.gr, Kariera.gr"
)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)

def register_help_handlers(app):
    app.add_handler(CommandHandler("help", help_cmd))
