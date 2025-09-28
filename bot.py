# bot.py
import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    constants,
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from db import SessionLocal, User, Keyword, JobSaved, JobDismissed

# ---------------- Logging ----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [bot] %(levelname)s: %(message)s")
logger = logging.getLogger("bot")

# ---------------- Config ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
TRIAL_DAYS = int(os.getenv("TRIAL_DAYS", "10"))

# ------------- Time helpers (fix naive vs aware) -------------
UTC = timezone.utc

def now_utc() -> datetime:
    return datetime.now(UTC)

def to_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Return UTC-aware datetime (tolerates None and naive)."""
    if dt is None:
        return None
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)

def fmt_dt(dt: Optional[datetime]) -> str:
    dt = to_aware(dt)
    return dt.strftime("%Y-%m-%d %H:%M:%S %Z") if dt else "None"

def user_active(u: User) -> bool:
    """A user is active if NOT blocked and has trial or license in the future."""
    if getattr(u, "is_blocked", False):
        return False
    now = now_utc()
    trial = to_aware(getattr(u, "trial_until", None))
    lic = to_aware(getattr(u, "access_until", None))
    return (trial and trial >= now) or (lic and lic >= now)

# ------------- Other helpers -------------------
def is_admin(update: Update) -> bool:
    return update.effective_user and update.effective_user.id == ADMIN_ID

async def ensure_user(db, tg_id: int) -> User:
    """Create user if missing. Trial starts on /start (όχι εδώ)."""
    u = db.query(User).filter_by(telegram_id=str(tg_id)).first()
    if not u:
        u = User(
            telegram_id=str(tg_id),
            countries="ALL",
        )
        db.add(u)
        db.commit()
        db.refresh(u)
    return u

def platforms_global() -> List[str]:
    return [
        "Freelancer.com",
        "Fiverr (affiliate links)",
        "PeoplePerHour (UK)",
        "Malt (FR/EU)",
        "Workana (ES/EU/LatAm)",
        "Upwork",
    ]

def platforms_gr() -> List[str]:
    return ["JobFind.gr", "Skywalker.gr", "Kariera.gr"]

def platforms_by_country(cc: Optional[str]) -> List[str]:
    cc = (cc or "").upper().strip()
    if not cc or cc == "ALL":
        return platforms_global() + platforms_gr()
    if cc == "GR":
        return platforms_gr()
    return platforms_global()

def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Add Keywords", callback_data="menu:addkeywords"),
            InlineKeyboardButton("⚙️ Settings", callback_data="menu:settings"),
        ],
        [
            InlineKeyboardButton("📖 Help", callback_data="menu:help"),
            InlineKeyboardButton("📬 Contact", callback_data="menu:contact"),
        ],
    ])

def features_block() -> str:
    return (
        "✨ *Features*\n"
        "• Realtime job alerts (Freelancer API)\n"
        "• Affiliate-wrapped *Proposal* & *Original* links\n"
        "• Budget shown + USD conversion\n"
        "• ⭐ *Keep* / 🗑 *Delete* buttons\n"
        "• 10-day free trial, extend via admin\n"
        "• Multi-keyword search (single/all modes)\n"
        "• Platforms by country (incl. GR boards)"
    )

def help_text(is_admin_flag: bool) -> str:
    txt = (
        "📖 *Help / How it works*\n\n"
        "1️⃣ Add keywords with `/addkeyword python telegram` (or use the menu)\n"
        "2️⃣ Set countries with `/setcountry US,UK` *(or `ALL`)*\n"
        "3️⃣ Save a proposal template with `/setproposal <text>`\n"
        "   Placeholders: `{jobtitle}`, `{experience}`, `{stack}`, `{budgettime}`, `{portfolio}`, `{name}`\n"
        "4️⃣ When a job arrives you can:\n"
        "   ⭐ *Keep* — save it\n"
        "   🗑 *Delete* — remove the message & mute that job\n"
        "   💼 *Proposal* — direct affiliate link to job\n"
        "   🔗 *Original* — same affiliate-wrapped job link\n\n"
        "🔎 `/mysettings` to check filters & trial/license\n"
        "🧪 `/selftest` for a test card\n"
        "🌍 `/platforms CC` to see platforms per country (e.g. `/platforms GR`)\n\n"
        "🧰 *Shortcuts*\n"
        "• `/keywords` or `/listkeywords` — list keywords\n"
        "• `/delkeyword <kw>` — delete one\n"
        "• `/clearkeywords` — delete all\n\n"
        "🛰 *Platforms*\n"
        "• *Global*: " + ", ".join(platforms_global()) + "\n"
        "• *Greece*: " + ", ".join(platforms_gr())
    )
    if is_admin_flag:
        txt += (
            "\n\n🛡 *Admin*\n"
            "• `/stats` — users/active\n"
            "• `/grant <telegram_id> <days>` — give license\n"
            "• `/reply <telegram_id> <message>` — reply to a user"
        )
    return txt

def settings_text(u: User) -> str:
    kws = ", ".join(k.keyword for k in u.keywords) if u.keywords else "(none)"
    start = fmt_dt(getattr(u, "created_at", None))
    trial = fmt_dt(getattr(u, "trial_until", None))
    lic = fmt_dt(getattr(u, "access_until", None))
    active = "✅" if user_active(u) else "❌"
    blocked = "✅" if getattr(u, "is_blocked", False) else "❌"
    return (
        "🛠 *Your Settings*\n\n"
        f"• Keywords: {kws}\n"
        f"• Countries: {u.countries or 'ALL'}\n"
        f"• Proposal template: {(u.proposal_template[:40] + '…') if u.proposal_template else '(none)'}\n\n"
        f"🟢 Start date: {start}\n"
        f"🎁 Trial ends: {trial}\n"
        f"🔒 License until: {lic}\n"
        f"• Active: {active}\n"
        f"• Blocked: {blocked}\n\n"
        "🛰 *Platforms monitored:*\n"
        "• Global: " + ", ".join(platforms_global()) + "\n"
        "• Greece: " + ", ".join(platforms_gr()) + "\n\n"
        "ℹ️ For extension, contact the admin."
    )

# ---------------- Commands ----------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Single central card with: welcome + short description + features + buttons.
    Trial starts here on first /start.
    """
    db = SessionLocal()
    try:
        u = await ensure_user(db, update.effective_user.id)

        # Start trial on first /start
        if not getattr(u, "trial_until", None):
            u.trial_until = now_utc() + timedelta(days=TRIAL_DAYS)
            db.commit()

        description = (
            "Automatically finds matching freelance jobs from top platforms and "
            "sends you instant alerts with affiliate-safe links."
        )

        text = (
            "👋 *Welcome to Freelancer Alert Bot!*\n\n"
            f"🎁 You have a *{TRIAL_DAYS}-day free trial*.\n"
            f"{description}\n\n"
            + features_block() +
            "\n\nUse /help to see all commands."
        )

        await update.message.reply_text(
            text,
            parse_mode=constants.ParseMode.MARKDOWN,
            disable_web_page_preview=True,
            reply_markup=main_menu_kb(),
        )
    finally:
        db.close()

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        help_text(is_admin(update)),
        parse_mode=constants.ParseMode.MARKDOWN,
        disable_web_page_preview=True
    )

async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    txt = f"🆔 Your Telegram ID: `{u.id}`\n👤 Name: {u.full_name}\n"
    txt += f"🔗 Username: @{u.username}\n" if u.username else "🔗 Username: (none)\n"
    if is_admin(update):
        txt += "\n⭐ You are *ADMIN*."
    else:
        txt += "\n👤 You are a regular user."
    await update.message.reply_text(txt, parse_mode=constants.ParseMode.MARKDOWN)

async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        u = await ensure_user(db, update.effective_user.id)
        await update.message.reply_text(
            settings_text(u),
            parse_mode=constants.ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
    finally:
        db.close()

# -------- Keywords --------
async def addkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Usage: /addkeyword <kw1> <kw2> ...")
    db = SessionLocal()
    try:
        u = await ensure_user(db, update.effective_user.id)
        added = 0
        for raw in context.args:
            kw = raw.strip()
            if not kw:
                continue
            exists = db.query(Keyword).filter_by(user_id=u.id, keyword=kw).first()
            if not exists:
                db.add(Keyword(user_id=u.id, keyword=kw))
                added += 1
        db.commit()
        await update.message.reply_text(f"✅ Added {added} keyword(s).")
    finally:
        db.close()

async def listkeywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        u = await ensure_user(db, update.effective_user.id)
        kws = ", ".join(k.keyword for k in u.keywords) if u.keywords else "(none)"
        await update.message.reply_text(f"Your keywords: {kws}")
    finally:
        db.close()

async def delkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Usage: /delkeyword <keyword>")
    kw = context.args[0]
    db = SessionLocal()
    try:
        u = await ensure_user(db, update.effective_user.id)
        row = db.query(Keyword).filter_by(user_id=u.id, keyword=kw).first()
        if row:
            db.delete(row)
            db.commit()
            await update.message.reply_text(f"🗑 Deleted keyword '{kw}'.")
        else:
            await update.message.reply_text(f"Not found: '{kw}'.")
    finally:
        db.close()

async def clearkeywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        u = await ensure_user(db, update.effective_user.id)
        for k in list(u.keywords):
            db.delete(k)
        db.commit()
        await update.message.reply_text("🧹 All keywords cleared.")
    finally:
        db.close()

# -------- Proposal template / countries --------
async def setproposal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").split(" ", 1)
    if len(text) < 2 or not text[1].strip():
        return await update.message.reply_text("Usage: /setproposal <your proposal text with placeholders>")
    prop = text[1].strip()
    db = SessionLocal()
    try:
        u = await ensure_user(db, update.effective_user.id)
        u.proposal_template = prop
        db.commit()
        await update.message.reply_text("💾 Proposal template saved.")
    finally:
        db.close()

async def setcountry_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = (update.message.text or "").split(" ", 1)
    val = raw[1].strip() if len(raw) > 1 else "ALL"
    db = SessionLocal()
    try:
        u = await ensure_user(db, update.effective_user.id)
        u.countries = val
        db.commit()
        await update.message.reply_text(f"🌍 Countries set to: {val}")
    finally:
        db.close()

# -------- Platforms --------
async def platforms_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cc = context.args[0] if context.args else "ALL"
    lst = platforms_by_country(cc)
    txt = f"🌍 Platforms for *{cc.upper()}*:\n• " + "\n• ".join(lst)
    await update.message.reply_text(txt, parse_mode=constants.ParseMode.MARKDOWN)

# -------- Self-test --------
async def selftest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kw = "TEST"
    job_id = f"selftest-{kw.lower()}"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💼 Proposal", url="https://www.freelancer.com"),
         InlineKeyboardButton("🔗 Original", url="https://www.freelancer.com")],
        [InlineKeyboardButton("⭐ Keep", callback_data=f"save:{job_id}"),
         InlineKeyboardButton("🗑 Delete", callback_data=f"dismiss:{job_id}")]
    ])
    text = (
        "🧪 *[TEST]* Example job card\n\n"
        "👤 Source: *Freelancer*\n"
        "🧾 Type: *Fixed*\n"
        "💰 Budget: *100–300 USD*\n"
        "💵 ~ $100.00–$300.00 USD\n"
        "📨 Bids: *12*\n"
        "🕒 Posted: *0s ago*\n\n"
        f"Keyword matched: *{kw}*"
    )
    await update.message.reply_text(text, parse_mode=constants.ParseMode.MARKDOWN, reply_markup=kb)

# -------- Keep / Delete callbacks --------
async def save_job_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, job_id = (q.data or "").split(":", 1)
    db = SessionLocal()
    try:
        u = await ensure_user(db, update.effective_user.id)
        exists = db.query(JobSaved).filter_by(user_id=u.id, job_id=job_id).first()
        if not exists:
            db.add(JobSaved(user_id=u.id, job_id=job_id))
            db.commit()
        await q.answer("Saved ✅", show_alert=False)
    finally:
        db.close()

async def dismiss_job_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, job_id = (q.data or "").split(":", 1)
    db = SessionLocal()
    try:
        u = await ensure_user(db, update.effective_user.id)
        exists = db.query(JobDismissed).filter_by(user_id=u.id, job_id=job_id).first()
        if not exists:
            db.add(JobDismissed(user_id=u.id, job_id=job_id))
            db.commit()
    finally:
        db.close()
    try:
        await q.message.delete()
    except Exception:
        pass

# -------- Contact / Admin reply --------
async def contact_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Send me a message with: /contact <your message>")
    msg = " ".join(context.args)
    u = update.effective_user
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📩 *Contact* from `{u.id}` ({u.full_name}):\n\n{msg}",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        await update.message.reply_text("✅ Sent to admin. You'll receive a reply here.")
    except Exception:
        await update.message.reply_text("Could not deliver your message to admin.")

async def reply_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if len(context.args) < 2:
        return await update.message.reply_text("Usage: /reply <telegram_id> <message>")
    target = context.args[0]
    text = " ".join(context.args[1:])
    try:
        await context.bot.send_message(chat_id=target, text=f"👨‍💼 Admin reply:\n\n{text}")
        await update.message.reply_text("✅ Delivered.")
    except Exception as e:
        await update.message.reply_text(f"Failed to deliver: {e}")

# -------- Admin --------
async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    db = SessionLocal()
    try:
        users = db.query(User).all()
        active = sum(1 for u in users if user_active(u))
        txt = f"👥 Users: {len(users)} (active: {active})"
        await update.message.reply_text(txt)
    finally:
        db.close()

async def grant_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if len(context.args) < 2:
        return await update.message.reply_text("Usage: /grant <telegram_id> <days>")
    uid = context.args[0]
    days = int(context.args[1])
    db = SessionLocal()
    try:
        u = db.query(User).filter_by(telegram_id=uid).first()
        if not u:
            return await update.message.reply_text("User not found.")
        until = now_utc() + timedelta(days=days)
        u.access_until = until
        db.commit()
        await update.message.reply_text(f"✅ Granted until {until.strftime('%Y-%m-%d')} to {uid}.")
    finally:
        db.close()

# -------- Inline menu callbacks --------
async def button_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    db = SessionLocal()
    try:
        u = await ensure_user(db, update.effective_user.id)
        chat_id = q.message.chat_id
        if data == "menu:addkeywords":
            await context.bot.send_message(chat_id, "Use /addkeyword <kw1> <kw2> …")
        elif data == "menu:settings":
            await context.bot.send_message(
                chat_id,
                settings_text(u),
                parse_mode=constants.ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
        elif data == "menu:help":
            await context.bot.send_message(
                chat_id,
                help_text(is_admin(update)),
                parse_mode=constants.ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
        elif data == "menu:contact":
            await context.bot.send_message(chat_id, "Send a message to admin: /contact <your message>")
    finally:
        db.close()

# ---------------- Build Application ----------------
def build_application() -> Application:
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Core / user commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("whoami", whoami_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))
    app.add_handler(CommandHandler("platforms", platforms_cmd))

    # keywords
    app.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app.add_handler(CommandHandler(["keywords", "listkeywords"], listkeywords_cmd))
    app.add_handler(CommandHandler("delkeyword", delkeyword_cmd))
    app.add_handler(CommandHandler("clearkeywords", clearkeywords_cmd))

    # templates / country
    app.add_handler(CommandHandler("setproposal", setproposal_cmd))
    app.add_handler(CommandHandler("setcountry", setcountry_cmd))

    # test
    app.add_handler(CommandHandler("selftest", selftest_cmd))

    # contact
    app.add_handler(CommandHandler("contact", contact_cmd))

    # admin
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("grant", grant_cmd))
    app.add_handler(CommandHandler("reply", reply_cmd))

    # callbacks
    app.add_handler(CallbackQueryHandler(button_cb, pattern=r"^menu:(addkeywords|settings|help|contact)$"))
    app.add_handler(CallbackQueryHandler(save_job_cb, pattern=r"^save:.+"))
    app.add_handler(CallbackQueryHandler(dismiss_job_cb, pattern=r"^dismiss:.+"))

    return app


# Standalone run with polling (for local dev)
if __name__ == "__main__":
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is not set.")
    app = build_application()
    logger.info("Running bot with polling (dev mode).")
    app.run_polling(drop_pending_updates=True)
