# bot.py
# -----------------------------------------------------------------------------
# Stable bot with HTML messages, global error handler and the original UI layout.
# -----------------------------------------------------------------------------
import os
import logging
from typing import Optional

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler,
    CallbackQueryHandler, ContextTypes,
)

from db import SessionLocal, User, Keyword, Job, SavedJob, JobSent

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ADMIN_ID  = os.getenv("ADMIN_ID", "")

# ---------------- helpers ----------------
def ensure_user_sync(tg_id: str, name: str, username: Optional[str]) -> User:
    """Create/update user synchronously (no async DB)."""
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.telegram_id == tg_id).one_or_none()
        if not u:
            u = User(telegram_id=tg_id, name=name, username=username or None)
            db.add(u)
            db.commit()
            db.refresh(u)
        else:
            changed = False
            if u.name != name:
                u.name = name
                changed = True
            if u.username != (username or None):
                u.username = username or None
                changed = True
            if changed:
                db.commit()
        return u
    finally:
        db.close()

# ---------------- commands ----------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        _ = ensure_user_sync(
            str(update.effective_user.id),
            update.effective_user.full_name,
            update.effective_user.username,
        )
    except Exception as e:
        log.warning("ensure_user failed: %s", e)

    hero = (
        "👋 <b>Welcome to Freelancer Alert Bot!</b>\n\n"
        "🎁 You have a <b>10-day free trial</b>.\n"
        "Automatically finds matching freelance jobs from top platforms and sends you "
        "instant alerts with affiliate-safe links.\n\n"
        "Use /help to see how it works."
    )

    # main menu – same layout as πριν
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Add Keywords", callback_data="nav:addk"),
            InlineKeyboardButton("⚙️ Settings",     callback_data="nav:settings"),
        ],
        [
            InlineKeyboardButton("📖 Help",   callback_data="nav:help"),
            InlineKeyboardButton("💾 Saved",  callback_data="nav:saved"),
        ],
        [
            InlineKeyboardButton("📨 Contact", callback_data="nav:contact"),
        ],
    ])
    await update.effective_chat.send_message(hero, reply_markup=kb, parse_mode="HTML")

    features = (
        "✨ <b>Features</b>\n"
        "• Realtime job alerts (Freelancer API)\n"
        "• Affiliate-wrapped <b>Proposal &amp; Original</b> links\n"
        "• Budget shown + USD conversion\n"
        "• ⭐ Keep / 🗑️ Delete buttons\n"
        "• 10-day free trial, extend via admin\n"
        "• Multi-keyword search (single/all modes)\n"
        "• Platforms by country (incl. GR boards)\n"
    )
    await update.effective_chat.send_message(features, parse_mode="HTML")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (
        "🧭 <b>Help / How it works</b>\n"
        "1) Add keywords with <code>/addkeyword python, telegram</code>\n"
        "2) Set your countries with <code>/setcountry US,UK</code> (or <b>ALL</b>)\n"
        "3) Save a proposal template with <code>/setproposal &lt;text&gt;</code>\n"
        "4) When a job arrives you can: ⭐ Keep / 🗑️ Delete / 📦 Proposal / 🔗 Original\n\n"
        "• Use <code>/mysettings</code> anytime to check your filters and proposal.\n"
        "• <code>/selftest</code> for a test job.\n"
        "• <code>/platforms CC</code> to see platforms by country (e.g., <code>/platforms GR</code>).\n"
    )
    await update.effective_chat.send_message(txt, parse_mode="HTML")

async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.telegram_id == str(update.effective_user.id)).one_or_none()
        if not u:
            await update.effective_chat.send_message("No settings yet. Add keywords with /addkeyword.", parse_mode="HTML")
            return
        kw = ", ".join(sorted([k.keyword for k in (u.keywords or [])])) or "(none)"
        txt = (
            "🛠️ <b>Your Settings</b>\n"
            f"• Keywords: {kw}\n"
            f"• Countries: {u.countries or 'ALL'}\n"
            f"• Proposal template: {(u.proposal_template or '(none)')}\n\n"
            f"🟢 Active: {'✅' if not u.is_blocked else '❌'}\n"
            f"⛔ Blocked: {'✅' if u.is_blocked else '❌'}\n"
        )
        await update.effective_chat.send_message(txt, parse_mode="HTML")
    finally:
        db.close()

async def selftest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Μικρή δοκιμαστική κάρτα, ίδιο layout κουμπιών
    text = (
        "<b>[TEST] Example job card</b>\n\n"
        "Source: Freelancer\n"
        "Type: Fixed\n"
        "Budget: 100–300 USD\n"
        "~ $100.00–$300.00 USD\n"
        "Bids: 12\n"
        "Posted: 0s ago\n\n"
        "Keyword matched: TEST"
    )
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📦 Proposal", url="https://example.com"),
            InlineKeyboardButton("🔗 Original", url="https://example.com"),
        ],
        [
            InlineKeyboardButton("⭐ Keep",   callback_data="keep:test"),
            InlineKeyboardButton("🗑️ Delete", callback_data="del:test"),
        ],
    ])
    await update.effective_chat.send_message(text, reply_markup=kb, parse_mode="HTML")

# ---------------- callbacks ----------------
async def button_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    try:
        await q.answer()
    except Exception:
        pass

    data = (q.data or "")
    if data.startswith("keep:"):
        try:
            # Αν είναι πραγματικό job id
            job_id = int(data.split(":", 1)[1])
            db = SessionLocal()
            try:
                j = db.query(Job).filter(Job.id == job_id).one_or_none()
                u = db.query(User).filter(User.telegram_id == str(update.effective_user.id)).one_or_none()
                if j and u:
                    already = db.query(SavedJob).filter(SavedJob.user_id == u.id, SavedJob.job_id == j.id).one_or_none()
                    if not already:
                        db.add(SavedJob(user_id=u.id, job_id=j.id))
                        db.commit()
                    if q.message:
                        q.message.edit_reply_markup(
                            reply_markup=InlineKeyboardMarkup([
                                [InlineKeyboardButton("📦 Proposal", url=j.proposal_url or j.url),
                                 InlineKeyboardButton("🔗 Original", url=j.original_url or j.url)],
                                [InlineKeyboardButton("⭐ Kept", callback_data=f"kept:{job_id}"),
                                 InlineKeyboardButton("🗑️ Delete", callback_data=f"del:{job_id}")],
                            ])
                        )
            finally:
                db.close()
        except Exception as e:
            log.warning("keep cb error: %s", e)
        return

    if data.startswith("del:"):
        try:
            if q.message:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=q.message.message_id)
        except Exception as e:
            log.warning("delete cb error: %s", e)
        return

# ---------------- error handler ----------------
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Μην αφήνουμε exceptions να γυρίζουν 500 στον webhook
    log.exception("Handler error", exc_info=context.error)
    try:
        if isinstance(update, Update) and update.effective_chat:
            await context.bot.send_message(update.effective_chat.id, "⚠️ Oops—something went wrong. Please try again.")
    except Exception:
        pass

# ---------------- app builder ----------------
def build_application() -> Application:
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is empty.")
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))
    app.add_handler(CommandHandler("selftest", selftest_cmd))
    app.add_handler(CallbackQueryHandler(button_cb))

    app.add_error_handler(on_error)
    log.info("PTB application ready.")
    return app
