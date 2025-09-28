# bot.py
import os
import re
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Tuple

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

from db import SessionLocal, User, Keyword, JobSaved, JobDismissed, ensure_schema

# ---------------- Logging ----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [bot] %(levelname)s: %(message)s")
logger = logging.getLogger("bot")

# Ensure DB schema on bot startup
ensure_schema()

# ---------------- Config ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
TRIAL_DAYS = int(os.getenv("TRIAL_DAYS", "10"))

# Affiliate helpers (for /saved “Open” links)
FREELANCER_REF_CODE = os.getenv("FREELANCER_REF_CODE", "").strip()  # e.g. "apstld"
AFFILIATE_PREFIX    = os.getenv("AFFILIATE_PREFIX", "").strip()

def affiliate_wrap(url: str) -> str:
    return f"{AFFILIATE_PREFIX}{url}" if AFFILIATE_PREFIX else url

def aff_for_source(source: str, url: str) -> str:
    if source == "freelancer" and FREELANCER_REF_CODE and "freelancer.com" in url:
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}f={FREELANCER_REF_CODE}"
    return affiliate_wrap(url)

# ------------- Time helpers -------------
UTC = timezone.utc
def now_utc() -> datetime:
    return datetime.now(UTC)

def to_aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)

def fmt_dt(dt: Optional[datetime]) -> str:
    dt = to_aware(dt)
    return dt.strftime("%Y-%m-%d %H:%M:%S %Z") if dt else "None"

def user_active(u: User) -> bool:
    if getattr(u, "is_blocked", False):
        return False
    now = now_utc()
    trial = to_aware(getattr(u, "trial_until", None))
    lic = to_aware(getattr(u, "access_until", None))
    return (trial and trial >= now) or (lic and lic >= now)

# ------------- Helpers -------------------
def is_admin(update: Update) -> bool:
    return update.effective_user and update.effective_user.id == ADMIN_ID

async def ensure_user(db, tg_id: int) -> User:
    u = db.query(User).filter_by(telegram_id=str(tg_id)).first()
    if not u:
        u = User(telegram_id=str(tg_id), countries="ALL")
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
        [
            InlineKeyboardButton("⭐ Saved", callback_data="menu:saved"),
        ]
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
        "1️⃣ Add keywords with `/addkeyword python, logo, \"lighting study\"`\n"
        "   • Use *comma* to separate many. Without a comma, the full text becomes *one* keyword.\n"
        "2️⃣ Set countries with `/setcountry US,UK` (or `ALL`)\n"
        "3️⃣ Save a proposal template with `/setproposal <text>`\n"
        "   Placeholders: `{jobtitle}`, `{experience}`, `{stack}`, `{budgettime}`, `{portfolio}`, `{name}`\n"
        "4️⃣ When a job arrives:\n"
        "   ⭐ *Keep* — save it (see `/saved`)\n"
        "   🗑 *Delete* — remove & mute that job\n"
        "   💼 *Proposal* — affiliate link\n"
        "   🔗 *Original* — affiliate-wrapped link\n\n"
        "🔎 `/mysettings` to review filters & trial/license\n"
        "🧪 `/selftest` for a sample card\n"
        "🌍 `/platforms CC` to see platforms by country (e.g. `/platforms GR`)\n"
        "⭐ `/saved` to view your saved jobs\n\n"
        "🧰 *Shortcuts*\n"
        "• `/keywords` or `/listkeywords` — list keywords\n"
        "• `/delkeyword <kw>` — delete one (case-insensitive)\n"
        "• `/clearkeywords` — delete all\n\n"
        "🛰 *Platforms*\n"
        "• *Global*: " + ", ".join(platforms_global()) + "\n"
        "• *Greece*: " + ", ".join(platforms_gr())
    )
    if is_admin_flag:
        txt += (
            "\n\n🛡 *Admin*\n"
            "• `/stats` — users/active\n"
            "• `/grant <telegram_id> <days>` — license\n"
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

# --------- Keyword parsing (comma-first; accepts any Unicode/Greek) ---------
def parse_keywords_from_text(full_text: str) -> List[str]:
    """
    Rules:
    - If commas exist, split by comma -> many keywords.
    - If NO commas, treat the remainder as ONE keyword (phrase allowed).
    - Strip surrounding quotes (single/double).
    - Deduplicate case-insensitively.
    """
    parts = full_text.split(" ", 1)
    raw = parts[1] if len(parts) > 1 else ""
    raw = raw.strip()

    def strip_quotes(s: str) -> str:
        if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
            return s[1:-1].strip()
        return s

    items: List[str] = []
    if "," in raw:
        items = [strip_quotes(p.strip()) for p in raw.split(",")]
    else:
        if raw:
            items = [strip_quotes(raw)]

    seen = set()
    out = []
    for item in items:
        if not item:
            continue
        key = item.casefold()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out

# ---------------- Commands ----------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        u = await ensure_user(db, update.effective_user.id)
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
    txt += "\n⭐ You are *ADMIN*." if is_admin(update) else "\n👤 You are a regular user."
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
    full_text = update.message.text or ""
    kws = parse_keywords_from_text(full_text)
    if not kws:
        return await update.message.reply_text('Usage: /addkeyword python, logo, "lighting study"')

    db = SessionLocal()
    try:
        u = await ensure_user(db, update.effective_user.id)
        existing = db.query(Keyword).filter_by(user_id=u.id).all()
        existing_set = {k.keyword.casefold() for k in existing}

        added = 0
        for kw in kws:
            if kw.casefold() in existing_set:
                continue
            db.add(Keyword(user_id=u.id, keyword=kw))
            existing_set.add(kw.casefold())
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
    full_text = update.message.text or ""
    target = full_text.split(" ", 1)[1].strip() if " " in full_text else ""
    if not target:
        return await update.message.reply_text("Usage: /delkeyword <keyword>")

    db = SessionLocal()
    try:
        u = await ensure_user(db, update.effective_user.id)
        row = None
        for k in u.keywords:
            if k.keyword.casefold() == target.casefold():
                row = k
                break
        if row:
            db.delete(row)
            db.commit()
            await update.message.reply_text(f"🗑 Deleted keyword '{row.keyword}'.")
        else:
            await update.message.reply_text(f"Not found: '{target}'.")
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

# -------- Saved list (/saved) --------
PAGE_SIZE = 5

def job_url_from_id(job_id: str) -> Tuple[Optional[str], Optional[str]]:
    """Return (url, source) if we can reconstruct it from the id, else (None, None)."""
    if job_id.startswith("freelancer-"):
        m = re.match(r"^freelancer-(\d+)$", job_id)
        if m:
            pid = m.group(1)
            url = f"https://www.freelancer.com/projects/{pid}"
            return aff_for_source("freelancer", url), "freelancer"
    # fiverr-* ids (daily) have no specific job
    return None, None

def build_saved_view(items: List[str], page: int) -> Tuple[str, InlineKeyboardMarkup]:
    total = len(items)
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(1, min(page, pages))

    start = (page - 1) * PAGE_SIZE
    chunk = items[start:start + PAGE_SIZE]

    lines = [f"⭐ *Saved jobs* — page {page}/{pages}", ""]
    kb_rows = []

    if not chunk:
        lines.append("_No saved jobs yet._")
    else:
        for jid in chunk:
            url, src = job_url_from_id(jid)
            lines.append(f"• `{jid}`")
            row = []
            if url:
                row.append(InlineKeyboardButton("🔗 Open", url=url))
            row.append(InlineKeyboardButton("🗑 Delete", callback_data=f"saved:del:{jid}:{page}"))
            kb_rows.append(row)

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"saved:page:{page-1}"))
    if page < pages:
        nav.append(InlineKeyboardButton("➡️ Next", callback_data=f"saved:page:{page+1}"))
    if nav:
        kb_rows.append(nav)

    kb = InlineKeyboardMarkup(kb_rows) if kb_rows else None
    text = "\n".join(lines)
    return text, kb

async def saved_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        u = await ensure_user(db, update.effective_user.id)
        rows = db.query(JobSaved).filter_by(user_id=u.id).order_by(JobSaved.created_at.desc()).all()
        items = [r.job_id for r in rows]
        text, kb = build_saved_view(items, page=1)
        await update.message.reply_text(
            text, parse_mode=constants.ParseMode.MARKDOWN, reply_markup=kb, disable_web_page_preview=True
        )
    finally:
        db.close()

async def saved_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data or ""
    db = SessionLocal()
    try:
        u = await ensure_user(db, update.effective_user.id)
        rows = db.query(JobSaved).filter_by(user_id=u.id).order_by(JobSaved.created_at.desc()).all()
        items = [r.job_id for r in rows]

        if data.startswith("saved:page:"):
            page = int(data.split(":")[2])
            text, kb = build_saved_view(items, page)
            await q.edit_message_text(text, parse_mode=constants.ParseMode.MARKDOWN, reply_markup=kb, disable_web_page_preview=True)
            await q.answer()
            return

        if data.startswith("saved:del:"):
            _, _, jid, page_s = data.split(":", 3)
            page = int(page_s)
            row = db.query(JobSaved).filter_by(user_id=u.id, job_id=jid).first()
            if row:
                db.delete(row)
                db.commit()
            rows = db.query(JobSaved).filter_by(user_id=u.id).order_by(JobSaved.created_at.desc()).all()
            items = [r.job_id for r in rows]
            text, kb = build_saved_view(items, page)
            try:
                await q.edit_message_text(text, parse_mode=constants.ParseMode.MARKDOWN, reply_markup=kb, disable_web_page_preview=True)
            except Exception:
                await q.message.reply_text(text, parse_mode=constants.ParseMode.MARKDOWN, reply_markup=kb, disable_web_page_preview=True)
            await q.answer("Deleted")
            return

    finally:
        db.close()

# -------- Contact / Admin reply --------
async def contact_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Send a message to the admin with: /contact <your message>")
    msg = " ".join(context.args)
    u = update.effective_user
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📩 *Contact* from `{u.id}` ({u.full_name}):\n\n{msg}",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        await update.message.reply_text("✅ Message delivered to admin. You'll receive a reply here.")
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
            await context.bot.send_message(chat_id, 'Use /addkeyword python, logo, "lighting study"')
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
            await context.bot.send_message(chat_id, "Send a message to the admin: /contact <your message>")
        elif data == "menu:saved":
            rows = db.query(JobSaved).filter_by(user_id=u.id).order_by(JobSaved.created_at.desc()).all()
            items = [r.job_id for r in rows]
            text, kb = build_saved_view(items, page=1)
            await context.bot.send_message(chat_id, text, parse_mode=constants.ParseMode.MARKDOWN, reply_markup=kb, disable_web_page_preview=True)
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
    app.add_handler(CommandHandler("saved", saved_cmd))

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
    app.add_handler(CallbackQueryHandler(button_cb, pattern=r"^menu:(addkeywords|settings|help|contact|saved)$"))
    app.add_handler(CallbackQueryHandler(save_job_cb, pattern=r"^save:.+"))
    app.add_handler(CallbackQueryHandler(dismiss_job_cb, pattern=r"^dismiss:.+"))
    app.add_handler(CallbackQueryHandler(saved_cb, pattern=r"^saved:(page|del):"))

    return app


if __name__ == "__main__":
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is not set.")
    app = build_application()
    logging.info("Running bot with polling (dev mode).")
    app.run_polling(drop_pending_updates=True)
