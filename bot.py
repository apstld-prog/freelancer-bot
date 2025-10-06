# bot.py
import os
import logging
from datetime import timedelta
from typing import Optional

from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
)
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

from db import get_session, now_utc, User, Keyword, SavedJob  # δεν αλλάζω το schema
from feedsstatus_handler import register_feedsstatus_handler  # <-- μόνο αυτό προστέθηκε

log = logging.getLogger("bot")
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_ID = os.getenv("ADMIN_TELEGRAM_ID", "")

# ---------------- UI blocks ----------------
def main_menu_kb(is_admin: bool) -> InlineKeyboardMarkup:
    row1 = [
        InlineKeyboardButton("➕ Add Keywords", callback_data="addkw"),
        InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
    ]
    row2 = [
        InlineKeyboardButton("📖 Help", callback_data="help"),
        InlineKeyboardButton("💾 Saved", callback_data="saved"),
    ]
    row3 = [InlineKeyboardButton("📬 Contact", callback_data="contact")]
    rows = [row1, row2, row3]
    if is_admin:
        rows.append([InlineKeyboardButton("🛠️ Admin", callback_data="admin")])
    return InlineKeyboardMarkup(rows)

FEATURES_TEXT = (
    "✨ *Features*\n"
    "• Realtime job alerts (Freelancer API)\n"
    "• Affiliate-wrapped *Proposal* & *Original* links\n"
    "• Budget shown + USD conversion\n"
    "• ⭐ Keep / 🗑️ Delete buttons\n"
    "• 10-day free trial, extend via admin\n"
    "• Multi-keyword search (single/all modes)\n"
    "• Platforms by country (incl. GR boards)\n"
)

def welcome_block(name: str) -> str:
    return (
        f"👋 *Welcome to Freelancer Alert Bot!*\n\n"
        f"🎁 You have a *10-day free trial*.\n"
        "Automatically finds matching freelance jobs from top platforms and sends you instant alerts with affiliate-safe links.\n\n"
        "Use /help to see how it works."
    )

# ---------------- Utility ----------------
async def ensure_user(context: ContextTypes.DEFAULT_TYPE, tg_id: str,
                      name: str, username: Optional[str]) -> User:
    with get_session() as db:
        u = db.query(User).filter(User.telegram_id == str(tg_id)).one_or_none()
        if u is None:
            now = now_utc()
            u = User(
                telegram_id=str(tg_id),
                name=name or "",
                username=username or "",
                started_at=now,
                trial_until=now + timedelta(days=10),
                access_until=None,
                is_blocked=False,
            )
            db.add(u)
            db.commit()
            db.refresh(u)
        else:
            # keep the record up-to-date
            changed = False
            if name and u.name != name:
                u.name = name; changed = True
            if username and u.username != username:
                u.username = username; changed = True
            if changed:
                db.commit()
        return u

def is_admin(update: Update) -> bool:
    return update.effective_user and str(update.effective_user.id) == str(ADMIN_ID)

# ---------------- Handlers ----------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    await ensure_user(context, str(user.id), user.full_name, user.username)
    kb = main_menu_kb(is_admin(update))
    await update.effective_chat.send_message(
        welcome_block(user.first_name or "there"),
        reply_markup=kb,
        parse_mode="Markdown",
    )
    # Features κάτω από το κεντρικό παράθυρο, όπως θες
    await update.effective_chat.send_message(FEATURES_TEXT, parse_mode="Markdown")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "*Commands*\n"
        "/start — main menu\n"
        "/keywords foo, bar — add multiple keywords (comma-separated)\n"
        "/whoami — show your Telegram info\n"
        "\n_Admin only:_ /feedsstatus"
    )
    await update.effective_chat.send_message(text, parse_mode="Markdown")

async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    u = update.effective_user
    if not u:
        return
    txt = (f"🆔 Your Telegram ID: `{u.id}`\n"
           f"👤 Name: {u.full_name}\n"
           f"🔗 Username: @{u.username}" if u.username else "🔗 Username: (none)")
    await update.effective_chat.send_message(txt, parse_mode="Markdown")

async def keywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # παίρνουμε όλο το μήνυμα μετά την εντολή, χωρίζουμε με κόμμα
    raw = (update.message.text or "").split(" ", 1)
    if len(raw) == 1:
        await update.effective_chat.send_message("Usage: /keywords word1, word2, ...")
        return
    to_add = [w.strip() for w in raw[1].split(",") if w.strip()]
    if not to_add:
        await update.effective_chat.send_message("No keywords detected.")
        return
    uid = str(update.effective_user.id)
    with get_session() as db:
        user = db.query(User).filter(User.telegram_id == uid).one()
        # αποθήκευση χωρίς διπλότυπα (case-insensitive)
        have = {k.keyword.lower() for k in user.keywords}
        added = 0
        for k in to_add:
            if k.lower() in have:
                continue
            db.add(Keyword(user_id=user.id, keyword=k))
            added += 1
        db.commit()
        fresh = ", ".join(sorted([k.keyword for k in user.keywords], key=str.lower))
    await update.effective_chat.send_message(f"Your keywords: {fresh}")

# βασικά callback buttons (δεν αλλάζω ροή)
async def button_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.callback_query:
        return
    q = update.callback_query
    await q.answer()
    data = q.data

    if data == "help":
        await help_cmd(update, context)
        return

    if data == "settings":
        # απλή, αναλυτική κάρτα settings (όπως στη φωτό)
        uid = str(update.effective_user.id)
        with get_session() as db:
            u = db.query(User).filter(User.telegram_id == uid).one()
            kws = ", ".join(k.keyword for k in u.keywords) or "(none)"
            start = getattr(u, "started_at", None)
            trial = u.trial_until
            license_until = u.access_until
            active = (bool(trial) and trial >= now_utc()) or (bool(license_until) and license_until >= now_utc())
            blocked = bool(u.is_blocked)
        text = (
            "🛠 *Your Settings*\n"
            f"• Keywords: {kws}\n"
            f"• Countries: ALL\n"
            f"• Proposal template: (none)\n\n"
            f"🟢 Start date: {start or 'n/a'}\n"
            f"🗓 Trial ends: {trial or 'None'}\n"
            f"🎫 License until: {license_until or 'None'}\n"
            f"✅ Active: {'✅' if active else '❌'}\n"
            f"⛔ Blocked: {'✅' if blocked else '❌'}\n\n"
            "🌐 *Platforms monitored:*\n"
            "• Global: Freelancer.com, Fiverr (affiliate links), PeoplePerHour (UK), Malt (FR/EU), Workana (ES/EU/LatAm), Upwork\n"
            "• Greece: JobFind.gr, Skywalker.gr, Kariera.gr\n\n"
            "📝 For extension, contact the admin."
        )
        await q.message.reply_text(text, parse_mode="Markdown")
        return

    if data == "saved":
        uid = str(update.effective_user.id)
        with get_session() as db:
            u = db.query(User).filter(User.telegram_id == uid).one()
            saved = db.query(SavedJob).filter(SavedJob.user_id == u.id).order_by(SavedJob.created_at.desc()).all()
        if not saved:
            await q.message.reply_text("No saved jobs yet.")
            return
        # Λίστα με Open/Delete για κάθε γραμμή
        rows = []
        for s in saved[:10]:
            rows.append([InlineKeyboardButton("🔗 Open", url=s.url),
                         InlineKeyboardButton("🗑 Delete", callback_data=f"del_saved:{s.id}")])
        await q.message.reply_text(
            "⭐ *Saved jobs* — page 1/1",
            reply_markup=InlineKeyboardMarkup(rows),
            parse_mode="Markdown",
        )
        return

    if data.startswith("del_saved:"):
        sid = data.split(":", 1)[1]
        with get_session() as db:
            db.query(SavedJob).filter(SavedJob.id == sid).delete()
            db.commit()
        await q.message.reply_text("Deleted.")
        return

    if data == "contact":
        await q.message.reply_text("✍️ Please type your message for the admin. I’ll forward it right away.")
        return

    if data == "admin":
        if not is_admin(update):
            await q.message.reply_text("Admin only.")
            return
        await q.message.reply_text("Admin panel: /feedsstatus")
        return

# message relay προς admin (reply keyboard logic παραμένει όπως έχεις)
async def text_relay(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or update.message.text.startswith("/"):
        return
    # forward to admin
    if ADMIN_ID:
        u = update.effective_user
        header = f"📨 *Message from user*\nID: `{u.id}`\nName: {u.full_name}\nUsername: @{u.username or '—'}"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("↩️ Reply", callback_data=f"replyto:{u.id}"),
             InlineKeyboardButton("🚫 Decline", callback_data=f"decline:{u.id}")]
        ])
        await context.bot.send_message(chat_id=int(ADMIN_ID), text=header, parse_mode="Markdown")
        await context.bot.send_message(chat_id=int(ADMIN_ID), text=update.message.text, reply_markup=kb)
    await update.message.reply_text("✅ Sent to admin.")

async def admin_reply_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.callback_query:
        return
    q = update.callback_query
    await q.answer()
    data = q.data
    if data.startswith("replyto:"):
        uid = data.split(":", 1)[1]
        context.user_data["reply_to"] = uid
        await q.message.reply_text(f"Type your reply to user `{uid}` and send.", parse_mode="Markdown")
        return
    if data.startswith("decline:"):
        uid = data.split(":", 1)[1]
        await context.bot.send_message(chat_id=int(uid), text="❌ Admin declined the conversation.")
        await q.message.reply_text("Declined.")
        return

async def admin_reply_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return
    target = context.user_data.get("reply_to")
    if not target:
        return
    await context.bot.send_message(chat_id=int(target), text=f"💬 Admin: {update.message.text}")
    # κουμπιά και στον user για reply/decline
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("↩️ Reply", callback_data=f"reply_admin:{update.effective_user.id}"),
         InlineKeyboardButton("🚫 Decline", callback_data=f"decline_admin:{update.effective_user.id}")]
    ])
    await context.bot.send_message(chat_id=int(target), text="You can reply or decline:", reply_markup=kb)
    context.user_data["reply_to"] = None

async def user_reply_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.callback_query:
        return
    q = update.callback_query
    await q.answer()
    data = q.data
    if data.startswith("reply_admin:"):
        context.user_data["reply_to_admin"] = ADMIN_ID
        await q.message.reply_text("Type your reply to the admin and send.")
    elif data.startswith("decline_admin:"):
        await context.bot.send_message(chat_id=int(ADMIN_ID), text="User declined the conversation.")
        await q.message.reply_text("Conversation closed.")

async def user_reply_text_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if "reply_to_admin" not in context.user_data:
        return
    await context.bot.send_message(chat_id=int(ADMIN_ID), text=f"💬 User: {update.message.text}")
    context.user_data.pop("reply_to_admin", None)
    await update.message.reply_text("✅ Sent to admin.")

# ---------------- Build app ----------------
def build_application() -> Application:
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # core commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("whoami", whoami_cmd))
    app.add_handler(CommandHandler("keywords", keywords_cmd))

    # feedsstatus (admin only) – εγγραφή handler χωρίς να αλλάξουμε κάτι άλλο
    register_feedsstatus_handler(app)

    # callbacks & relay
    app.add_handler(CallbackQueryHandler(admin_reply_router, pattern="^(replyto:|decline:)"))
    app.add_handler(CallbackQueryHandler(user_reply_to_admin, pattern="^(reply_admin:|decline_admin:)"))
    app.add_handler(CallbackQueryHandler(button_cb))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_reply_text))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, user_reply_text_to_admin))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_relay))

    return app
