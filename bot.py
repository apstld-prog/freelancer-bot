# ================= BOT (RESET PACK v0) =================
import os, logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, Application, CommandHandler, CallbackQueryHandler, ContextTypes
from sqlalchemy import text as _t

from db import get_session, get_or_create_user_by_tid
from ui_texts import welcome_full, help_footer

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

def is_admin_user(tid: int) -> bool:
    admins = [x.strip() for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
    return str(tid) in admins

def main_keyboard(is_admin: bool=False) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("+ Add Keywords", callback_data="act:addkw"),
         InlineKeyboardButton("⚙️ Settings", callback_data="act:settings")],
        [InlineKeyboardButton("🆘 Help", callback_data="act:help"),
         InlineKeyboardButton("💾 Saved", callback_data="act:saved")],
        [InlineKeyboardButton("📨 Contact", callback_data="act:contact"),
         InlineKeyboardButton("🔥 Admin", callback_data="act:admin")]
    ])

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    days = int(os.getenv("TRIAL_DAYS", "10"))
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        s.execute(_t('UPDATE "user" SET trial_start=COALESCE(trial_start, NOW()) WHERE id=:id'), {"id": u.id})
        s.execute(_t('UPDATE "user" SET trial_end=COALESCE(trial_end, NOW() + (:d || \' days\')::interval) WHERE id=:id'), {"id": u.id, "d": str(days)})
        s.commit()
        row = s.execute(_t('SELECT trial_start, trial_end, license_until, is_active, is_blocked FROM "user" WHERE id=:id'), {"id": u.id}).fetchone()

    await update.effective_chat.send_message(
        welcome_full(days),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=main_keyboard(is_admin_user(update.effective_user.id)),
    )

    if row:
        ts, te, lic, active, blocked = row
        def b(x): return "✅" if x else "❌"
        msg = (f"<b>🧾 Your access</b>\n"
               f"• Start: {ts}\n"
               f"• Trial ends: {te} UTC\n"
               f"• License until: {lic}\n"
               f"• Active: {b(active)}    Blocked: {b(blocked)}")
        await update.effective_chat.send_message(msg, parse_mode=ParseMode.HTML)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    txt = "Use the menu below to manage your alerts and settings." + help_footer(24, admin=is_admin_user(uid))
    await update.effective_chat.send_message(txt, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

async def cb_mainmenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q: return
    data = q.data or ""
    await q.answer()
    if data == "act:addkw":
        await q.message.reply_text("Send: /addkeyword word1, word2")
    elif data == "act:settings":
        await q.message.reply_text("Open /mysettings to view your settings.")
    elif data == "act:help":
        await help_cmd(update, context)
    elif data == "act:saved":
        await q.message.reply_text("Open /saved to view your saved jobs.")
    elif data == "act:contact":
        await q.message.reply_text(os.getenv("CONTACT_HANDLE", "@your_username"))
    elif data == "act:admin":
        if is_admin_user(update.effective_user.id):
            await q.message.reply_text("/users, /grant <id> <days>, /block <id>, /unblock <id>, /broadcast <text>, /feedstatus")
        else:
            await q.message.reply_text("You're not an admin.")
    elif data.startswith("job:"):
        if data == "job:save":
            try: await q.message.delete()
            except Exception: pass
            await q.message.chat.send_message("⭐ Saved to your list.")
        elif data == "job:delete":
            try: await q.message.delete()
            except Exception: pass
            await q.message.chat.send_message("🗑️ Deleted.")
        else:
            await q.message.chat.send_message("Unknown action.")
    else:
        await q.message.reply_text("Unknown action.")

def build_application() -> Application:
    token = os.getenv("BOT_TOKEN")
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(cb_mainmenu))
    log.info("✅ Handlers registered.")
    return app

if __name__ == "__main__":
    app = build_application()
    app.run_polling()
