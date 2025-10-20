import logging
import asyncio
import json
import os
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.constants import ParseMode

from utils import (
    load_users,
    save_users,
    format_jobs,
    load_keywords,
    save_keywords,
    is_admin,
)
from platform_freelancer import get_items as freelancer_get_items
from platform_peopleperhour import get_items as pph_get_items

logger = logging.getLogger(__name__)
users = load_users()
keywords = load_keywords()
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))


# --- START ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in users:
        users[uid] = {"joined": datetime.now().isoformat()}
        save_users(users)
    await update.message.reply_text(
        "👋 Καλώς ήρθες στο Freelancer Bot!\n\n"
        "Θα λαμβάνεις αυτόματα νέες αγγελίες από διάφορες πλατφόρμες.\n"
        "Πληκτρολόγησε /help για οδηγίες."
    )


# --- HELP ---
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📘 Διαθέσιμες εντολές:\n"
        "• /start - Επανεκκίνηση bot\n"
        "• /help - Εμφάνιση βοήθειας\n"
        "• /keywords - Προβολή λέξεων-κλειδιών\n"
        "• /add <λέξη> - Προσθήκη λέξης\n"
        "• /remove <λέξη> - Αφαίρεση λέξης\n"
        "• /feedstatus - Κατάσταση συστήματος\n"
        "• /search <λέξη> - Αναζήτηση PeoplePerHour χειροκίνητα"
    )


# --- KEYWORDS LIST ---
async def keywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kw = ", ".join(keywords) if keywords else "(καμία)"
    await update.message.reply_text(f"🔑 Ενεργές λέξεις-κλειδιά:\n{kw}")


# --- ADD KEYWORD ---
async def add_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Χρήση: /add <λέξη>")
        return
    word = " ".join(context.args).lower().strip()
    if word not in keywords:
        keywords.append(word)
        save_keywords(keywords)
        await update.message.reply_text(f"✅ Προστέθηκε: {word}")
    else:
        await update.message.reply_text("Η λέξη υπάρχει ήδη.")


# --- REMOVE KEYWORD ---
async def remove_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Χρήση: /remove <λέξη>")
        return
    word = " ".join(context.args).lower().strip()
    if word in keywords:
        keywords.remove(word)
        save_keywords(keywords)
        await update.message.reply_text(f"❌ Αφαιρέθηκε: {word}")
    else:
        await update.message.reply_text("Η λέξη δεν υπάρχει.")


# --- FEED STATUS ---
async def feedstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (
        "🩵 Κατάσταση Συστήματος\n"
        "Freelancer ✅\n"
        "PeoplePerHour ✅\n"
        "Skywalker ✅\n"
        "Render Server ✅"
    )
    await update.message.reply_text(txt)


# --- ADMIN BROADCAST ---
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, ADMIN_ID):
        await update.message.reply_text("🚫 Δεν έχεις δικαιώματα.")
        return
    if not context.args:
        await update.message.reply_text("Χρήση: /broadcast <μήνυμα>")
        return
    msg = " ".join(context.args)
    count = 0
    for uid in users.keys():
        try:
            await context.bot.send_message(chat_id=uid, text=msg)
            count += 1
            await asyncio.sleep(0.1)
        except Exception:
            pass
    await update.message.reply_text(f"📢 Εστάλη σε {count} χρήστες.")


# --- SELFTEST ---
async def selftest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Έλεγχος Freelancer και PeoplePerHour...")
    try:
        f_jobs = freelancer_get_items(["logo"])[:2]
        p_jobs = pph_get_items(["logo"])[:2]
        txt = f"✅ Freelancer: {len(f_jobs)}\n✅ PeoplePerHour: {len(p_jobs)}"
    except Exception as e:
        txt = f"⚠️ Σφάλμα: {e}"
    await update.message.reply_text(txt)


# --- NEW: /search command (PeoplePerHour manual test) ---
async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manual PeoplePerHour keyword search via proxy."""
    if not context.args:
        await update.message.reply_text(
            "Χρήση:\n<code>/search logo</code>\nΑναζήτηση στο PeoplePerHour μέσω proxy.",
            parse_mode=ParseMode.HTML,
        )
        return

    keyword = " ".join(context.args).strip()
    await update.message.reply_text(f"🔎 Αναζήτηση για <b>{keyword}</b>...", parse_mode=ParseMode.HTML)

    try:
        from platform_peopleperhour import get_items
        jobs = get_items([keyword])
    except Exception as e:
        await update.message.reply_text(f"⚠️ Σφάλμα: {e}")
        return

    if not jobs:
        await update.message.reply_text("Δεν βρέθηκαν αποτελέσματα.")
        return

    for j in jobs[:5]:
        title = j.get("title", "(χωρίς τίτλο)")
        budget = j.get("budget", "—")
        currency = j.get("currency", "")
        usd = j.get("budget_usd", "")
        desc = j.get("desc", "")
        link = j.get("url", "")

        text = (
            f"<b>{title}</b>\n"
            f"<b>Προϋπολογισμός:</b> {budget} {currency}"
            + (f" (~${usd} USD)" if usd else "")
            + "\n"
            f"<b>Πηγή:</b> PeoplePerHour\n\n"
            f"{desc[:400]}..."
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Άνοιγμα", url=link)]])
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


# --- BUILD APPLICATION ---
def build_application():
    app = ApplicationBuilder().token(os.environ.get("TELEGRAM_TOKEN")).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("keywords", keywords_cmd))
    app.add_handler(CommandHandler("add", add_keyword))
    app.add_handler(CommandHandler("remove", remove_keyword))
    app.add_handler(CommandHandler("feedstatus", feedstatus_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("selftest", selftest))
    app.add_handler(CommandHandler("search", search_cmd))  # ✅ Νέα εντολή

    return app


if __name__ == "__main__":
    application = build_application()
    application.run_polling()
