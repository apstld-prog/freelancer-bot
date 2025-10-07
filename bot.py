# bot.py
# -----------------------------------------------------------------------------
# Telegram bot – ΔΕΝ αλλάζω layout/μηνύματα σου, μόνο το DB session handling.
# -----------------------------------------------------------------------------

import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove,
)
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
)

from db_async import get_session, get_session_sync  # <— ADAPTER ΕΔΩ
from db import User, Keyword, Job, SavedJob, JobSent, now_utc

from feedsstatus_handler import register_feedsstatus_handler  # για /feedsstatus

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ADMIN_ID  = os.getenv("ADMIN_ID", "")  # string

# ---------------- utilities ----------------

def is_admin(update: Update) -> bool:
    try:
        return str(update.effective_user.id) == str(ADMIN_ID)
    except Exception:
        return False

def md_esc(s: str) -> str:
    return s.replace("_", r"\_").replace("*", r"\*").replace("[", r"\[").replace("`", r"\`")

# ---------------- ensure user ----------------

async def ensure_user(context: ContextTypes.DEFAULT_TYPE, tg_id: str, name: str, username: Optional[str]) -> User:
    async with get_session() as db:
        u = db.query(User).filter(User.telegram_id == tg_id).one_or_none()
        if not u:
            u = User(telegram_id=tg_id, name=name, username=username or None)
            db.add(u); db.commit(); db.refresh(u)
        else:
            changed = False
            if u.name != name: u.name = name; changed = True
            if u.username != (username or None): u.username = username or None; changed = True
            if changed: db.commit()
        return u

# ---------------- commands ----------------

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = await ensure_user(context, str(update.effective_user.id), update.effective_user.full_name, update.effective_user.username)

    # ΤΟ ΔΙΚΟ ΣΟΥ WELCOME “ΣΤΗΣΙΜΟ” – δεν το αλλάζω
    hero = (
        "👋 *Welcome to Freelancer Alert Bot!*\n\n"
        "🎁 You have a *10-day free trial*.\n"
        "Automatically finds matching freelance jobs from top platforms and sends you instant alerts with affiliate-safe links.\n\n"
        "Use /help to see how it works."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Keywords", callback_data="nav:addk"),
         InlineKeyboardButton("⚙️ Settings", callback_data="nav:settings")],
        [InlineKeyboardButton("📖 Help", callback_data="nav:help"),
         InlineKeyboardButton("💾 Saved", callback_data="nav:saved")],
        [InlineKeyboardButton("📨 Contact", callback_data="nav:contact")],
    ])
    await update.effective_chat.send_message(hero, parse_mode="Markdown", reply_markup=kb)

    features = (
        "✨ *Features*\n"
        "• Realtime job alerts (Freelancer API)\n"
        "• Affiliate-wrapped *Proposal & Original* links\n"
        "• Budget shown + USD conversion\n"
        "• ⭐ Keep / 🗑️ Delete buttons\n"
        "• 10-day free trial, extend via admin\n"
        "• Multi-keyword search (single/all modes)\n"
        "• Platforms by country (incl. GR boards)\n"
    )
    await update.effective_chat.send_message(features, parse_mode="Markdown")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (
        "🧭 *Help / How it works*\n"
        "1) /addkeyword _python, telegram_\n"
        "2) /setcountry _US,UK_ (or ALL)\n"
        "3) /setproposal `<text>` with placeholders etc.\n"
        "4) When a job arrives you can: ⭐ Keep / 🗑️ Delete / 📦 Proposal / 🔗 Original\n\n"
        "• Use /mysettings anytime.\n"
        "• /selftest for a test job.\n"
        "• /platforms CC to see platforms by country.\n\n"
        "📋 *Platforms monitored*\n"
        "Global: Freelancer.com, PeoplePerHour, Malt, Workana, Guru, 99designs, Toptal*, Codeable*, YunoJuno*, Worksome*, twago, freelancermap\n"
        "Greece: JobFind.gr, Skywalker.gr, Kariera.gr\n"
    )
    await update.effective_chat.send_message(txt, parse_mode="Markdown")

async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with get_session() as db:
        u = db.query(User).filter(User.telegram_id == str(update.effective_user.id)).one()
        kw = ", ".join(sorted([k.keyword for k in (u.keywords or [])])) or "(none)"
        txt = (
            "🛠️ *Your Settings*\n"
            f"• Keywords: {md_esc(kw)}\n"
            f"• Countries: {u.countries or 'ALL'}\n"
            f"• Proposal template: {(u.proposal_template or '(none)')}\n\n"
            f"🟢 Active: {'✅' if not u.is_blocked else '❌'}\n"
            f"⛔ Blocked: {'✅' if u.is_blocked else '❌'}\n"
        )
        await update.effective_chat.send_message(txt, parse_mode="Markdown")

# -------------- callbacks (keep/delete/proposal/original κλπ.) --------------

async def button_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    data = q.data or ""
    if data.startswith("keep:"):
        job_id = int(data.split(":", 1)[1])
        async with get_session() as db:
            j = db.query(Job).filter(Job.id == job_id).one()
            u = db.query(User).filter(User.telegram_id == str(update.effective_user.id)).one()
            already = db.query(SavedJob).filter(SavedJob.user_id == u.id, SavedJob.job_id == j.id).one_or_none()
            if not already:
                db.add(SavedJob(user_id=u.id, job_id=j.id))
                db.commit()
        await q.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 Proposal", url=j.proposal_url or j.url),
             InlineKeyboardButton("🔗 Original", url=j.original_url or j.url)],
            [InlineKeyboardButton("⭐ Kept", callback_data=f"kept:{job_id}"),
             InlineKeyboardButton("🗑️ Delete", callback_data=f"del:{job_id}")],
        ]))
        return

    if data.startswith("del:"):
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=q.message.message_id)
        except Exception:
            pass
        return

# -------------- init --------------

def build_application() -> Application:
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))

    app.add_handler(CallbackQueryHandler(button_cb))

    # admin-only /feedsstatus
    register_feedsstatus_handler(app)

    return app
