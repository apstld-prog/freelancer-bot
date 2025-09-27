import os
import sys
import re
import atexit
import signal
import asyncio
import logging
import telegram
from typing import List, Dict

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
)

from db import SessionLocal, User, Keyword, JobSaved, JobDismissed, JobSent, AppLock

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
AFFILIATE_PREFIX = os.getenv("AFFILIATE_PREFIX", "")
ADMIN_ID = int(os.getenv("TELEGRAM_ADMIN_ID", "0"))
if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN is not set.")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [bot] %(levelname)s: %(message)s")
logger = logging.getLogger("freelancer-bot")
logger.info(f"Python runtime: {sys.version}")
logger.info(f"python-telegram-bot version: {getattr(telegram, '__version__', 'unknown')}")

_SPLIT_RE = re.compile(r"[,\n]+")

# --------- Platforms (για /help, /mysettings, /platforms) ---------
PLATFORM_LIST = [
    "🌍 *Global Freelancing*: Freelancer.com, PeoplePerHour (UK), Malt (FR/EU), Workana (ES/EU/LatAm), Fiverr Affiliates, Upwork",
    "🇬🇷 *Greek Job Boards*: JobFind.gr, Skywalker.gr, Kariera.gr",
]
PLATFORM_COUNTRY_MAP: Dict[str, List[str]] = {
    "GLOBAL": ["freelancer", "peopleperhour", "malt", "workana", "fiverr", "upwork"],
    "GR": ["jobfind", "skywalker", "kariera", "freelancer", "peopleperhour"],
    "UK": ["peopleperhour", "freelancer", "upwork"],
    "FR": ["malt", "freelancer", "upwork"],
    "DE": ["malt", "freelancer", "freelancermap"],
    "ES": ["workana", "freelancer", "peopleperhour"],
    "IT": ["malt", "freelancer", "peopleperhour"],
}

WELCOME = (
    "👋 *Welcome to Freelancer Alerts Bot!*\n\n"
    "Get real-time job alerts based on your keywords and country filters.\n\n"
    "👉 Use the menu below or commands to configure your settings."
)

HELP = (
    "📖 *Help / How it works*\n\n"
    "1️⃣ Add keywords with `/addkeyword python, telegram`\n"
    "2️⃣ Set your countries with `/setcountry US,UK` (or `ALL`)\n"
    "3️⃣ Save a proposal template with `/setproposal <text>`\n"
    "   Placeholders: {job_title}, {experience}, {stack}, {availability}, {step1}, {step2}, {step3}, {budget_time}, {portfolio}, {name}\n"
    "4️⃣ When a job arrives you can:\n"
    "   • ⭐ Save it\n"
    "   • 🙈 Dismiss it\n"
    "   • 💼 Proposal → *direct affiliate link to job*\n"
    "   • 🔗 Original → *same affiliate-wrapped job link*\n\n"
    "⚙️ `/mysettings` to check filters.\n"
    "🧪 `/selftest` for a test job.\n"
    "🌍 `/platforms [CC]` to see platforms by country (e.g. `/platforms GR`).\n\n"
    "📡 *Platforms currently supported:*\n" + "\n".join(PLATFORM_LIST)
)

# ---------------- Helpers ----------------
def is_admin(user_id: int) -> bool:
    return ADMIN_ID and user_id == ADMIN_ID

def normalize_kw_list(text: str) -> List[str]:
    out, seen = [], set()
    for part in _SPLIT_RE.split(text or ""):
        p = part.strip()
        if p and p.lower() not in seen:
            seen.add(p.lower()); out.append(p)
    return out

async def reply_usage(update: Update, text: str):
    await update.effective_message.reply_text(text)

def list_keywords(db, user_id: int) -> List[str]:
    rows = db.query(Keyword).filter_by(user_id=user_id).order_by(Keyword.keyword.asc()).all()
    return [r.keyword for r in rows]

async def ensure_user(db, telegram_id: int) -> User:
    row = db.query(User).filter_by(telegram_id=telegram_id).first()
    if not row:
        row = User(telegram_id=telegram_id, countries="ALL")
        db.add(row); db.commit(); db.refresh(row)
    return row

def main_menu_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("➕ Add Keywords", callback_data="menu:add"),
                InlineKeyboardButton("🛠 Settings", callback_data="menu:settings"),
            ],
            [InlineKeyboardButton("📖 Help", callback_data="menu:help")],
        ]
    )

# ---------------- Commands ----------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(WELCOME, reply_markup=main_menu_markup(), parse_mode="Markdown")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(HELP, reply_markup=main_menu_markup(), parse_mode="Markdown")

async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        user = await ensure_user(db, update.effective_user.id)
        kws = list_keywords(db, user.id)
        txt = "🛠 *Your Settings*\n\n"
        txt += f"• Keywords: {', '.join(kws) if kws else '(none)'}\n"
        txt += f"• Countries: {user.countries or 'ALL'}\n"
        txt += f"• Proposal template: {(user.proposal_template or '(none)')}\n\n"
        txt += "📡 *Platforms monitored:*\n" + "\n".join(PLATFORM_LIST)
        await update.effective_message.reply_text(txt, parse_mode="Markdown")
    finally:
        db.close()

async def setcountry_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        return await reply_usage(update, "Usage: /setcountry <US,UK,DE> or ALL")
    val = " ".join(args).upper().replace(" ", "")
    db = SessionLocal()
    try:
        user = await ensure_user(db, update.effective_user.id)
        user.countries = val
        db.commit()
        await update.effective_message.reply_text(f"✅ Countries set to: {val}")
    finally:
        db.close()

async def addkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text:
        return await reply_usage(update, "Usage: /addkeyword <word[,word2,...]>")
    new_kws = normalize_kw_list(text)
    if not new_kws:
        return await update.effective_message.reply_text("No valid keywords found.")
    db = SessionLocal()
    added = []
    try:
        user = await ensure_user(db, update.effective_user.id)
        existing = set(k.lower() for k in list_keywords(db, user.id))
        for kw in new_kws:
            if kw.lower() in existing:
                continue
            db.add(Keyword(user_id=user.id, keyword=kw)); added.append(kw)
        db.commit()
        await update.effective_message.reply_text(
            f"{'✅ Added: ' + ', '.join(added) if added else 'No new keywords (duplicates).'}"
        )
    finally:
        db.close()

async def keywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        user = await ensure_user(db, update.effective_user.id)
        kws = list_keywords(db, user.id)
        await update.effective_message.reply_text(
            "📚 Keywords:\n" + ("\n".join(f"• {k}" for k in kws) if kws else "(none)")
        )
    finally:
        db.close()

async def clearkeywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("✅ Confirm", callback_data="conf:clear_kws")],
         [InlineKeyboardButton("❌ Cancel", callback_data="conf:cancel")]]
    )
    await update.effective_message.reply_text("Are you sure you want to delete all keywords?", reply_markup=kb)

async def delkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await reply_usage(update, "Usage: /delkeyword <keyword>")
    name = " ".join(context.args).strip()
    db = SessionLocal()
    try:
        user = await ensure_user(db, update.effective_user.id)
        row = None
        for k in list_keywords(db, user.id):
            if k.lower() == name.lower():
                row = db.query(Keyword).filter_by(user_id=user.id, keyword=k).first()
                break
        if not row:
            return await update.effective_message.reply_text(f"Not found: {name}")
        db.delete(row); db.commit()
        await update.effective_message.reply_text(f"🗑 Deleted keyword: {name}")
    finally:
        db.close()

async def setproposal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args).strip()
    if not text:
        return await reply_usage(update, "Usage: /setproposal <text>")
    if len(text) > 6000:
        return await update.effective_message.reply_text("Template too long (max ~6000 chars).")
    db = SessionLocal()
    try:
        user = await ensure_user(db, update.effective_user.id)
        user.proposal_template = text
        db.commit()
        await update.effective_message.reply_text("✅ Proposal template saved.")
    finally:
        db.close()

async def savejob_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await reply_usage(update, "Usage: /savejob <job_id>")
    job_id = context.args[0][:64]
    db = SessionLocal()
    try:
        user = await ensure_user(db, update.effective_user.id)
        if not db.query(JobSaved).filter_by(user_id=user.id, job_id=job_id).first():
            db.add(JobSaved(user_id=user.id, job_id=job_id)); db.commit()
        await update.effective_message.reply_text(f"⭐ Saved job: {job_id}")
    finally:
        db.close()

async def dismissjob_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await reply_usage(update, "Usage: /dismissjob <job_id>")
    job_id = context.args[0][:64]
    db = SessionLocal()
    try:
        user = await ensure_user(db, update.effective_user.id)
        if not db.query(JobDismissed).filter_by(user_id=user.id, job_id=job_id).first():
            db.add(JobDismissed(user_id=user.id, job_id=job_id)); db.commit()
        await update.effective_message.reply_text(f"🙈 Dismissed job: {job_id}")
    finally:
        db.close()

# --- Menu / confirm callbacks ---
async def confirm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    if data == "conf:clear_kws":
        db = SessionLocal()
        try:
            user = await ensure_user(db, update.effective_user.id)
            db.query(Keyword).filter_by(user_id=user.id).delete()
            db.commit()
            await q.edit_message_text("✅ All keywords cleared.")
        finally:
            db.close()
    elif data == "conf:cancel":
        await q.edit_message_text("❌ Cancelled.")

async def button_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    if data == "menu:add":
        await q.message.reply_text("Use `/addkeyword <word[,word2,...]>` to add keywords.", parse_mode="Markdown")
    elif data == "menu:settings":
        await mysettings_cmd(update, context)
    elif data == "menu:help":
        await help_cmd(update, context)

# --- Diagnostics & Admin ---
async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    txt = (
        "🙋 *WhoAmI*\n\n"
        f"🆔 Your Telegram ID: `{user.id}`\n"
        f"👤 Name: {user.first_name or ''} {user.last_name or ''}\n"
        f"🔗 Username: @{user.username if user.username else '(none)'}"
    )
    await update.effective_message.reply_text(txt, parse_mode="Markdown")

def is_admin_msg(update: Update) -> bool:
    return is_admin(update.effective_user.id)

async def adminstats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_msg(update):
        return
    db = SessionLocal()
    try:
        user_count = db.query(User).count()
        keyword_count = db.query(Keyword).count()
        jobs_sent = db.query(JobSent).count()
        jobs_saved = db.query(JobSaved).count()
        jobs_dismissed = db.query(JobDismissed).count()
        text = (
            "📊 *Bot Statistics*\n\n"
            f"👥 Users: {user_count}\n"
            f"🔑 Keywords: {keyword_count}\n"
            f"📤 Jobs sent: {jobs_sent}\n"
            f"⭐ Jobs saved: {jobs_saved}\n"
            f"🙈 Jobs dismissed: {jobs_dismissed}\n"
        )
        await update.effective_message.reply_text(text, parse_mode="Markdown")
    finally:
        db.close()

async def adminusers_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_msg(update):
        return
    db = SessionLocal()
    try:
        users = db.query(User).all()
        lines = ["👥 *Registered Users*:"]
        for u in users:
            lines.append(f"• {u.telegram_id} | Countries: {u.countries or 'ALL'} | Keywords: {len(u.keywords)}")
        text = "\n".join(lines)
        await update.effective_message.reply_text(text, parse_mode="Markdown")
    finally:
        db.close()

async def selftest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    aff = os.getenv("AFFILIATE_PREFIX", "")
    if not aff:
        return await update.effective_message.reply_text("⚠️ AFFILIATE_PREFIX is not set.")
    sample_url = "https://www.freelancer.com/projects/python/telegram-bot-job-TEST"
    aff_url = f"{aff}{sample_url}"
    buttons = [
        [InlineKeyboardButton("⭐ Save", callback_data=f"save:TEST"),
         InlineKeyboardButton("🙈 Dismiss", callback_data=f"dismiss:TEST")],
        [InlineKeyboardButton("💼 Proposal", url=aff_url),
         InlineKeyboardButton("🔗 Original", url=aff_url)],
    ]
    keyboard = InlineKeyboardMarkup(buttons)
    text = "🧪 *Self-Test Job*\n\nThis is a test message to verify buttons and affiliate wrapping.\n\n🔗 [View Job]({})".format(aff_url)
    await update.effective_message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown", disable_web_page_preview=True)

async def platforms_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cc = (context.args[0].upper() if context.args else "GLOBAL")
    platforms = PLATFORM_COUNTRY_MAP.get(cc) or PLATFORM_COUNTRY_MAP["GLOBAL"]
    lines = [f"🌍 *Platforms for {cc}*"] + [f"• {p}" for p in platforms]
    await update.effective_message.reply_text("\n".join(lines), parse_mode="Markdown")

# ---------------- Singleton lock + webhook cleanup ----------------
def acquire_polling_lock() -> bool:
    db = SessionLocal()
    try:
        # καθάρισε παλιές εγγραφές αν θες — εδώ αφήνουμε μία ενεργή
        db.add(AppLock(name="polling"))
        db.commit()
        logger.info("Acquired DB polling lock.")
        return True
    except Exception:
        db.rollback()
        logger.error("Another instance holds the DB polling lock. Exiting to avoid conflict.")
        return False
    finally:
        db.close()

def release_polling_lock():
    db = SessionLocal()
    try:
        row = db.query(AppLock).filter_by(name="polling").first()
        if row:
            db.delete(row)
            db.commit()
            logger.info("Released DB polling lock.")
    except Exception:
        pass
    finally:
        db.close()

def setup_sig_handlers():
    def _graceful(*_):
        try:
            release_polling_lock()
        finally:
            os._exit(0)
    signal.signal(signal.SIGINT, _graceful)
    signal.signal(signal.SIGTERM, _graceful)
    atexit.register(release_polling_lock)

def main():
    # 1) singleton lock (αν αποτύχει -> τερματισμός)
    if not acquire_polling_lock():
        sys.exit(0)
    setup_sig_handlers()

    # 2) Χτύπα το API & σβήσε οποιοδήποτε webhook για να αποφύγουμε conflicts webhook vs polling
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    asyncio.run(app.bot.delete_webhook(drop_pending_updates=True))
    logger.info("Deleted webhook (if existed). Starting polling...")

    # 3) Δηλώσεις handlers
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))
    app.add_handler(CommandHandler("version", lambda u, c: u.effective_message.reply_text(
        f"🧪 Runtime\n• Python: {sys.version.split()[0]}\n• PTB: {getattr(telegram, '__version__', 'unknown')}\n• AFFILIATE_PREFIX set: {'yes' if AFFILIATE_PREFIX else 'no'}"
    )))
    app.add_handler(CommandHandler("selftest", selftest_cmd))
    app.add_handler(CommandHandler("platforms", platforms_cmd))
    app.add_handler(CommandHandler("setcountry", setcountry_cmd))
    app.add_handler(CommandHandler("setproposal", setproposal_cmd))
    app.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app.add_handler(CommandHandler("keywords", keywords_cmd))
    app.add_handler(CommandHandler("listkeywords", keywords_cmd))
    app.add_handler(CommandHandler("delkeyword", delkeyword_cmd))
    app.add_handler(CommandHandler("clearkeywords", clearkeywords_cmd))
    app.add_handler(CommandHandler("savejob", savejob_cmd))
    app.add_handler(CommandHandler("dismissjob", dismissjob_cmd))
    app.add_handler(CommandHandler("whoami", whoami_cmd))
    app.add_handler(CommandHandler("adminstats", adminstats_cmd))
    app.add_handler(CommandHandler("adminusers", adminusers_cmd))

    app.add_handler(CallbackQueryHandler(button_cb, pattern=r"^menu:"))
    app.add_handler(CallbackQueryHandler(confirm_cb, pattern=r"^conf:(clear_kws|cancel)$"))

    try:
        app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)
    finally:
        release_polling_lock()

if __name__ == "__main__":
    main()
