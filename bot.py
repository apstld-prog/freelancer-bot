import os
import sys
import re
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional

import telegram
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, Application, CommandHandler, CallbackQueryHandler, ContextTypes
)

from db import SessionLocal, User, Keyword, JobSaved, JobDismissed, JobSent, AppLock

# ------------ Config ------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
AFFILIATE_PREFIX = os.getenv("AFFILIATE_PREFIX", "")
ADMIN_ID = int(os.getenv("TELEGRAM_ADMIN_ID", "0"))
TRIAL_DAYS = int(os.getenv("TRIAL_DAYS", "10"))
if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN is not set.")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [bot] %(levelname)s: %(message)s")
logger = logging.getLogger("freelancer-bot")
logger.info(f"python-telegram-bot version: {getattr(telegram, '__version__', 'unknown')}")

_SPLIT_RE = re.compile(r"[,\n]+")

# --------- Platforms ---------
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
    f"🎁 *Free trial {TRIAL_DAYS} days* from the moment you press /start.\n"
    "After the trial you can request more access from the admin.\n\n"
    "👉 Use the menu below or commands to configure your settings."
)

HELP = (
    "📖 *Help / How it works*\n\n"
    "1️⃣ Add keywords with `/addkeyword python, telegram`\n"
    "2️⃣ View your keywords with `/keywords` or `/listkeywords`\n"
    "3️⃣ Delete one keyword with `/delkeyword <kw>`\n"
    "4️⃣ Clear all keywords with `/clearkeywords`\n"
    "5️⃣ Set your countries with `/setcountry US,UK` (or `ALL`)\n"
    "6️⃣ Save a proposal template with `/setproposal <text>`\n"
    "   Placeholders: {job_title}, {experience}, {stack}, {availability}, {step1}, {step2}, {step3}, {budget_time}, {portfolio}, {name}\n"
    "7️⃣ When a job arrives you can:\n"
    "   • ⭐ Save it  • 🙈 Dismiss it  • 💼 Proposal  • 🔗 Original\n\n"
    "ℹ️ `/status` to see your trial/license status.\n"
    "📨 `/contact <message>` to reach the admin.\n"
    "🧪 `/selftest` for a test job.\n"
    "🌍 `/platforms [CC]` to see platforms by country (e.g. `/platforms GR`).\n\n"
    "📡 *Platforms currently supported:*\n" + "\n".join(PLATFORM_LIST)
)

# ------------ Helpers ------------
def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def is_admin(user_id: int) -> bool:
    return ADMIN_ID and user_id == ADMIN_ID

def normalize_kw_list(text: str) -> List[str]:
    out, seen = [], set()
    for part in _SPLIT_RE.split(text or ""):
        p = part.strip()
        if p and p.lower() not in seen:
            seen.add(p.lower()); out.append(p)
    return out

def list_keywords(db, user_id: int) -> List[str]:
    rows = db.query(Keyword).filter_by(user_id=user_id).order_by(Keyword.keyword.asc()).all()
    return [r.keyword for r in rows]

async def ensure_user(db, telegram_id: int) -> User:
    row = db.query(User).filter_by(telegram_id=telegram_id).first()
    if not row:
        row = User(telegram_id=telegram_id, countries="ALL")
        db.add(row); db.commit(); db.refresh(row)
    return row

def user_is_active(u: User) -> (bool, Optional[str]):
    """Returns (is_active, reason)."""
    t = now_utc()
    if u.is_blocked:
        return False, "blocked"
    if u.access_until and u.access_until >= t:
        return True, None
    if u.trial_until and u.trial_until >= t:
        return True, None
    return False, "expired"

def human_left(dt: Optional[datetime]) -> str:
    if not dt:
        return "—"
    secs = (dt - now_utc()).total_seconds()
    if secs <= 0:
        return "expired"
    days = int(secs // 86400)
    hours = int((secs % 86400) // 3600)
    return f"{days}d {hours}h"

def main_menu_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("➕ Add Keywords", callback_data="menu:add"),
                InlineKeyboardButton("🛠 Settings", callback_data="menu:settings"),
            ],
            [
                InlineKeyboardButton("📖 Help", callback_data="menu:help"),
                InlineKeyboardButton("📨 Contact", callback_data="menu:contact"),
            ],
        ]
    )

# ------------ Commands (user) ------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        user = await ensure_user(db, update.effective_user.id)
        if not user.started_at:
            user.started_at = now_utc()
            user.trial_until = user.started_at + timedelta(days=TRIAL_DAYS)
            db.commit()
        await update.effective_message.reply_text(
            WELCOME + f"\n\n⏳ *Trial ends:* `{user.trial_until}` (UTC)",
            reply_markup=main_menu_markup(), parse_mode="Markdown"
        )
    finally:
        db.close()

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(HELP, reply_markup=main_menu_markup(), parse_mode="Markdown")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        u = await ensure_user(db, update.effective_user.id)
        active, reason = user_is_active(u)
        txt = (
            "🧾 *Your Access Status*\n\n"
            f"• Trial until: `{u.trial_until}` (left: {human_left(u.trial_until)})\n"
            f"• License until: `{u.access_until}` (left: {human_left(u.access_until)})\n"
            f"• Active: {'✅' if active else '❌'}"
        )
        if not active:
            txt += "\n\n📨 Use `/contact I need access` to reach the admin."
        await update.effective_message.reply_text(txt, parse_mode="Markdown")
    finally:
        db.close()

async def contact_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User sends a message that is forwarded to the admin."""
    if not ADMIN_ID:
        return await update.effective_message.reply_text("Admin is not configured.")
    msg = " ".join(context.args).strip()
    if not msg:
        return await update.effective_message.reply_text("Usage: /contact <your message>")
    user = update.effective_user
    text = f"📨 *Contact request*\nFrom: `{user.id}` {user.first_name or ''} @{user.username or '(none)'}\n\n{msg}"
    await context.bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode="Markdown")
    await update.effective_message.reply_text("✅ Message sent to admin. You will receive a reply here.")

# ------------ Admin commands ------------
async def adminhelp_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    txt = (
        "🛡 *Admin Commands*\n\n"
        "• `/adminstats` – Bot statistics (users, keywords, jobs sent/saved/dismissed)\n"
        "• `/adminusers` – List users (ID, countries, keywords)\n"
        "• `/grant <user_id> <days>` – Give license for N days\n"
        "• `/extend <user_id> <days>` – Extend license by N days\n"
        "• `/revoke <user_id>` – Revoke license (set expired)\n"
        "• `/reply <user_id> <text>` – Send a reply to a user\n"
        "• `/whoami` – Show your Telegram ID\n"
    )
    await update.effective_message.reply_text(txt, parse_mode="Markdown")

async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    txt = (
        "🙋 *WhoAmI*\n\n"
        f"🆔 Your Telegram ID: `{user.id}`\n"
        f"👤 Name: {user.first_name or ''} {user.last_name or ''}\n"
        f"🔗 Username: @{user.username if user.username else '(none)'}"
    )
    await update.effective_message.reply_text(txt, parse_mode="Markdown")

async def adminstats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
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
    if not is_admin(update.effective_user.id):
        return
    db = SessionLocal()
    try:
        users = db.query(User).all()
        lines = ["👥 *Registered Users*:"]
        for u in users:
            active, _ = user_is_active(u)
            lines.append(
                f"• {u.telegram_id} | Active: {'✅' if active else '❌'} | Trial: {u.trial_until} | Access: {u.access_until} | KW: {len(u.keywords)}"
            )
        await update.effective_message.reply_text("\n".join(lines), parse_mode="Markdown")
    finally:
        db.close()

async def grant_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if len(context.args) < 2:
        return await update.effective_message.reply_text("Usage: /grant <user_id> <days>")
    uid = int(context.args[0]); days = int(context.args[1])
    db = SessionLocal()
    try:
        u = db.query(User).filter_by(telegram_id=uid).first()
        if not u: return await update.effective_message.reply_text("User not found.")
        u.access_until = now_utc() + timedelta(days=days)
        u.is_blocked = False
        db.commit()
        await update.effective_message.reply_text(f"✅ Granted access to {uid} until {u.access_until} (UTC).")
    finally:
        db.close()

async def extend_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if len(context.args) < 2:
        return await update.effective_message.reply_text("Usage: /extend <user_id> <days>")
    uid = int(context.args[0]); days = int(context.args[1])
    db = SessionLocal()
    try:
        u = db.query(User).filter_by(telegram_id=uid).first()
        if not u: return await update.effective_message.reply_text("User not found.")
        base = u.access_until if u.access_until and u.access_until > now_utc() else now_utc()
        u.access_until = base + timedelta(days=days)
        db.commit()
        await update.effective_message.reply_text(f"🔁 Extended access for {uid} until {u.access_until} (UTC).")
    finally:
        db.close()

async def revoke_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        return await update.effective_message.reply_text("Usage: /revoke <user_id>")
    uid = int(context.args[0])
    db = SessionLocal()
    try:
        u = db.query(User).filter_by(telegram_id=uid).first()
        if not u: return await update.effective_message.reply_text("User not found.")
        u.access_until = now_utc() - timedelta(seconds=1)
        db.commit()
        await update.effective_message.reply_text(f"⛔ Revoked access for {uid}.")
    finally:
        db.close()

async def reply_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if len(context.args) < 2:
        return await update.effective_message.reply_text("Usage: /reply <user_id> <text>")
    uid = int(context.args[0])
    text = " ".join(context.args[1:])
    await context.bot.send_message(chat_id=uid, text=f"💬 *Admin reply:*\n\n{text}", parse_mode="Markdown")
    await update.effective_message.reply_text("✅ Sent.")

# ------------ Menu callbacks ------------
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
    elif data == "menu:contact":
        await q.message.reply_text("📨 Send a message with `/contact <your message>` and the admin will reply here.")

# ------------ User settings commands ------------
async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        user = await ensure_user(db, update.effective_user.id)
        kws = list_keywords(db, user.id)
        active, _ = user_is_active(user)
        txt = "🛠 *Your Settings*\n\n"
        txt += f"• Keywords: {', '.join(kws) if kws else '(none)'}\n"
        txt += f"• Countries: {user.countries or 'ALL'}\n"
        txt += f"• Proposal template: {(user.proposal_template or '(none)')}\n\n"
        txt += f"🎁 Trial until: `{user.trial_until}` (left: {human_left(user.trial_until)})\n"
        txt += f"🔑 License until: `{user.access_until}` (left: {human_left(user.access_until)})\n"
        txt += f"• Active: {'✅' if active else '❌'}\n\n"
        txt += "📡 *Platforms monitored:*\n" + "\n".join(PLATFORM_LIST)
        await update.effective_message.reply_text(txt, parse_mode="Markdown")
    finally:
        db.close()

# ------------ Keywords & countries ------------
async def setcountry_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        return await update.effective_message.reply_text("Usage: /setcountry <US,UK,DE> or ALL")
    val = " ".join(args).upper().replace(" ", "")
    db = SessionLocal()
    try:
        user = await ensure_user(db, update.effective_user.id)
        user.countries = val
        db.commit()
        await update.effective_message.reply_text(f"✅ Countries set to: {val}")
    finally:
        db.close()

async def setproposal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args).strip()
    if not text:
        return await update.effective_message.reply_text("Usage: /setproposal <text>")
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

async def addkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text:
        return await update.effective_message.reply_text("Usage: /addkeyword <word[,word2,...]>")
    new_kws = normalize_kw_list(text)
    if not new_kws:
        return await update.effective_message.reply_text("No valid keywords found.")
    db = SessionLocal()
    try:
        user = await ensure_user(db, update.effective_user.id)
        existing = set(k.lower() for k in list_keywords(db, user.id))
        added = []
        for kw in new_kws:
            if kw.lower() in existing: 
                continue
            db.add(Keyword(user_id=user.id, keyword=kw)); added.append(kw)
        db.commit()
        await update.effective_message.reply_text('✅ Added: ' + (', '.join(added) if added else '(none)'))
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
        return await update.effective_message.reply_text("Usage: /delkeyword <keyword>")
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

# ------------ Platforms ------------
async def platforms_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cc = (context.args[0].upper() if context.args else "GLOBAL")
    platforms = PLATFORM_COUNTRY_MAP.get(cc) or PLATFORM_COUNTRY_MAP["GLOBAL"]
    lines = [f"🌍 *Platforms for {cc}*"] + [f"• {p}" for p in platforms]
    await update.effective_message.reply_text("\n".join(lines), parse_mode="Markdown")

# ------------ PTB lifecycle ------------
async def _post_init(app: Application):
    await app.bot.delete_webhook(drop_pending_updates=True)
    logger.info("Webhook deleted via post_init.")

# ------------ Main ------------
def main():
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(_post_init)
        .build()
    )

    # User
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("contact", contact_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))
    app.add_handler(CommandHandler("platforms", platforms_cmd))

    # Settings/keywords
    app.add_handler(CommandHandler("setcountry", setcountry_cmd))
    app.add_handler(CommandHandler("setproposal", setproposal_cmd))
    app.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app.add_handler(CommandHandler("keywords", keywords_cmd))
    app.add_handler(CommandHandler("listkeywords", keywords_cmd))
    app.add_handler(CommandHandler("delkeyword", delkeyword_cmd))
    app.add_handler(CommandHandler("clearkeywords", clearkeywords_cmd))

    # Job actions (manual)
    app.add_handler(CommandHandler("savejob", lambda u, c: u.effective_message.reply_text("Use inline buttons in job posts.")))
    app.add_handler(CommandHandler("dismissjob", lambda u, c: u.effective_message.reply_text("Use inline buttons in job posts.")))

    # Admin
    app.add_handler(CommandHandler("adminhelp", adminhelp_cmd))
    app.add_handler(CommandHandler("adminstats", adminstats_cmd))
    app.add_handler(CommandHandler("adminusers", adminusers_cmd))
    app.add_handler(CommandHandler("grant", grant_cmd))
    app.add_handler(CommandHandler("extend", extend_cmd))
    app.add_handler(CommandHandler("revoke", revoke_cmd))
    app.add_handler(CommandHandler("reply", reply_cmd))
    app.add_handler(CommandHandler("whoami", whoami_cmd))

    # Callbacks
    app.add_handler(CallbackQueryHandler(button_cb, pattern=r"^menu:"))
    app.add_handler(CallbackQueryHandler(confirm_cb, pattern=r"^conf:(clear_kws|cancel)$"))

    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
