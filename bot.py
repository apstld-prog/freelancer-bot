import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, Application, CommandHandler, CallbackQueryHandler, ContextTypes
)

from db import ensure_schema, get_session, get_or_create_user_by_tid, list_user_keywords, add_user_keywords

log = logging.getLogger("bot")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN env var is required")

# ---------- UI bits kept as we locked ----------
def main_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ Settings", callback_data="act:settings")],
        [InlineKeyboardButton("🆘 Help", callback_data="act:help")]
    ])

def settings_card(u, kws: list[str]) -> str:
    kws_line = ", ".join(kws) if kws else "—"
    return (
        "🛠 <b>Your Settings</b>\n"
        f"• <b>Keywords</b>: {kws_line}\n"
        "• Countries: ALL\n"
        "• Proposal template: (none)\n"
    )

# ---------- Commands ----------

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as db:
        u = get_or_create_user_by_tid(db, update.effective_user.id)
        kws = list_user_keywords(db, u.id)
    txt = (
        "👋 Καλωσήρθες!\n"
        "• Πρόσθεσε λέξεις-κλειδιά: <code>/addkeyword logo, lighting</code>\n"
        "• Δες τις ρυθμίσεις σου: <code>/mysettings</code>\n"
        "• Βοήθεια: <code>/help</code>\n"
    )
    await update.message.reply_text(txt, parse_mode=ParseMode.HTML, reply_markup=main_menu_kb())

async def addkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # If user typed only /addkeyword show prompt
    if not context.args:
        await update.message.reply_text(
            "Δώσε λέξεις-κλειδιά χωρισμένες με κόμμα. Παράδειγμα:\n"
            "<code>/addkeyword logo, lighting</code>",
            parse_mode=ParseMode.HTML
        )
        return

    raw = " ".join(context.args)
    parts = [p.strip() for p in raw.split(",")]
    parts = [p for p in parts if p]

    with get_session() as db:
        u = get_or_create_user_by_tid(db, update.effective_user.id)
        inserted = add_user_keywords(db, u.id, parts)
        kws = list_user_keywords(db, u.id)

    msg = "✅ Προστέθηκαν {} νέες λέξεις.\n\n".format(inserted)
    msg += "Τρέχουσες λέξεις-κλειδιά:\n• " + (", ".join(kws) if kws else "—")
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as db:
        u = get_or_create_user_by_tid(db, update.effective_user.id)
        kws = list_user_keywords(db, u.id)
    await update.message.reply_text(
        settings_card(u, kws),
        parse_mode=ParseMode.HTML
    )

# ---------- Callbacks ----------

async def menu_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data or ""
    if data == "act:settings":
        with get_session() as db:
            u = get_or_create_user_by_tid(db, q.from_user.id)
            kws = list_user_keywords(db, u.id)
        await q.message.reply_text(settings_card(u, kws), parse_mode=ParseMode.HTML)
        await q.answer()
        return
    if data == "act:help":
        await q.message.reply_text(
            "ℹ️ Help / How it works\n"
            "1) /addkeyword python, telegram\n"
            "2) /mysettings",
            parse_mode=ParseMode.HTML
        )
        await q.answer()
        return
    await q.answer()

# ---------- Application ----------

def build_application() -> Application:
    ensure_schema()
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))
    app.add_handler(CallbackQueryHandler(menu_action_cb, pattern=r"^act:(settings|help)$"))

    log.info("Handlers ready: /start /addkeyword /mysettings + menu callbacks")
    return app
