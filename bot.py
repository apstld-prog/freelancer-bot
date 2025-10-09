# bot.py — full replacement (English-only UX + continuous user↔admin chat + keywords + admin fixes + safe scheduler)
import os
import logging
import asyncio
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Set, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# Try to import JobQueue (may exist but fail to init if extra not installed)
try:
    from telegram.ext import JobQueue  # type: ignore
except Exception:
    JobQueue = None  # type: ignore

# --- project-local modules (must exist in your repo) ---
from db import (
    ensure_schema,
    get_session,
    get_or_create_user_by_tid,
    list_user_keywords,
    add_user_keywords,
    User,
)
from config import ADMIN_IDS, TRIAL_DAYS, STATS_WINDOW_HOURS
from db_events import get_platform_stats

log = logging.getLogger("bot")
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = (
    os.getenv("TELEGRAM_BOT_TOKEN")
    or os.getenv("BOT_TOKEN")
    or os.getenv("TELEGRAM_TOKEN")
)
if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN env var is required")

ADMIN_ELEVATE_SECRET = os.getenv("ADMIN_ELEVATE_SECRET", "")  # optional secret for /sudo

# ======================================================================
# Admin helpers
# ======================================================================
def get_db_admin_ids() -> Set[int]:
    try:
        with get_session() as s:
            ids = [row.telegram_id for row in s.query(User).filter(getattr(User, "is_admin") == True).all()]  # noqa: E712
        return set(int(x) for x in ids if x)
    except Exception:
        return set()

def all_admin_ids() -> Set[int]:
    return set(int(x) for x in (ADMIN_IDS or [])) | get_db_admin_ids()

def is_admin_user(uid: int) -> bool:
    return uid in all_admin_ids()

# ======================================================================
# UI (English-only bot text)
# ======================================================================
def main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("➕ Add Keywords", callback_data="act:addkw"),
         InlineKeyboardButton("⚙️ Settings", callback_data="act:settings")],
        [InlineKeyboardButton("🆘 Help", callback_data="act:help"),
         InlineKeyboardButton("💾 Saved", callback_data="act:saved")],
        [InlineKeyboardButton("📨 Contact", callback_data="act:contact")],
    ]
    if is_admin:
        kb.append([InlineKeyboardButton("🔥 Admin", callback_data="act:admin")])
    return InlineKeyboardMarkup(kb)

def features_text() -> str:
    return (
        "<b>✨ Features</b>\n"
        "• Real-time job alerts (Freelancer API)\n"
        "• Affiliate-wrapped <b>Proposal</b> & <b>Original</b> links\n"
        "• Budget shown + USD conversion\n"
        "• ⭐ Keep / 🗑 Delete\n"
        "• 10-day free trial (extend via admin)\n"
        "• Multi-keyword search\n"
        "• Platforms by country (incl. GR boards)\n"
    )

HELP_EN = (
    "<b>🧭 Help / How it works</b>\n\n"
    "<b>1)</b> Add keywords with <code>/addkeyword</code> (comma-separated) or via the “Add Keywords” button.\n"
    "<b>2)</b> Set countries with <code>/setcountry</code> (e.g. <i>US,UK</i> or <i>ALL</i>).\n"
    "<b>3)</b> Save a proposal template with <code>/setproposal &lt;text&gt;</code> (placeholders supported).\n"
    "<b>4)</b> When a job arrives you can keep/delete it or open <b>Proposal</b>/<b>Original</b> link.\n\n"
    "Use <code>/mysettings</code> anytime. Try <code>/selftest</code> for a sample card.\n"
)

def help_footer(hours: int) -> str:
    return (
        "\n<b>🛰 Platforms monitored:</b>\n"
        "• Global: <a href=\"https://www.freelancer.com\">Freelancer.com</a> (affiliate), PeoplePerHour, Malt, Workana, Guru, 99designs, "
        "Toptal*, Codeable*, YunoJuno*, Worksome*, twago, freelancermap\n"
        "• Greece: <a href=\"https://www.jobfind.gr\">JobFind.gr</a>, "
        "<a href=\"https://www.skywalker.gr\">Skywalker.gr</a>, <a href=\"https://www.kariera.gr\">Kariera.gr</a>\n\n"
        "<b>👑 Admin:</b> /users /grant /block /unblock /broadcast /feedstatus (/feetstatus)\n"
        "<i>Link previews disabled for clean help.</i>\n"
    )

def welcome_text(expiry: Optional[datetime]) -> str:
    extra = f"\n<b>Free trial ends:</b> {expiry.strftime('%Y-%m-%d %H:%M UTC')}" if expiry else ""
    return (
        "<b>👋 Welcome to Freelancer Alert Bot!</b>\n\n"
        "🎁 You have a <b>10-day free trial</b>.\n"
        "The bot finds matching freelance jobs from top platforms and sends instant alerts."
        f"{extra}\n\nUse <code>/help</code> for instructions.\n"
    )

def settings_text(keywords: List[str], countries: str | None, proposal_template: str | None,
                  trial_start, trial_end, license_until, active: bool, blocked: bool) -> str:
    def b(v: bool) -> str: return "✅" if v else "❌"
    k = ", ".join(keywords) if keywords else "(none)"
    c = countries if countries else "ALL"
    pt = "(none)" if not proposal_template else "(saved)"
    ts = trial_start.isoformat().replace("+00:00", "Z") if trial_start else "—"
    te = trial_end.isoformat().replace("+00:00", "Z") if trial_end else "—"
    lic = "None" if not license_until else license_until.isoformat().replace("+00:00", "Z")
    return (
        "<b>🛠 Your Settings</b>\n"
        f"• <b>Keywords:</b> {k}\n"
        f"• <b>Countries:</b> {c}\n"
        f"• <b>Proposal template:</b> {pt}\n\n"
        f"<b>●</b> Start date: {ts}\n"
        f"<b>●</b> Trial ends: {te} UTC\n"
        f"<b>🔑</b> License until: {lic}\n"
        f"<b>✅ Active:</b> {b(active)}    <b>⛔ Blocked:</b> {b(blocked)}\n\n"
        "<b>🛰 Platforms monitored:</b> Global & GR boards.\n"
        "<i>For extension, contact the admin.</i>"
    )

# ======================================================================
# Keywords helpers
# ======================================================================
def parse_keywords_input(raw: str) -> List[str]:
    parts = [p.strip() for chunk in raw.split(",") for p in chunk.split() if p.strip()]
    seen, clean = set(), []
    for p in parts:
        key = p.lower()
        if key not in seen:
            seen.add(key); clean.append(p)
    return clean

def add_keywords_safe(db_session, user_id: int, keywords: List[str]) -> int:
    if not keywords:
        return 0
    inserted = 0
    try:
        res = add_user_keywords(db_session, user_id, keywords)  # try list signature
        inserted = int(res) if res is not None else 0
    except TypeError:
        try:
            res = add_user_keywords(db_session, user_id, ", ".join(keywords))  # fallback string signature
            inserted = int(res) if res is not None else 0
        except Exception:
            inserted = 0
    except Exception:
        inserted = 0

    # If helper didn't report, compute delta vs current list
    try:
        current = list_user_keywords(db_session, user_id) or []
        before = set([c.lower() for c in current])
        added = [k for k in keywords if k.lower() not in before]
        inserted = max(inserted, len(added))
    except Exception:
        pass
    return inserted

# ======================================================================
# Contact flow helpers (continuous chat)
# ======================================================================
def admin_contact_kb(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("💬 Reply", callback_data=f"adm:reply:{user_id}"),
             InlineKeyboardButton("❌ Decline", callback_data=f"adm:decline:{user_id}")],
            [InlineKeyboardButton("+30d", callback_data=f"adm:grant:{user_id}:30"),
             InlineKeyboardButton("+90d", callback_data=f"adm:grant:{user_id}:90"),
             InlineKeyboardButton("+180d", callback_data=f"adm:grant:{user_id}:180"),
             InlineKeyboardButton("+365d", callback_data=f"adm:grant:{user_id}:365")],
        ]
    )

def user_contact_hint() -> str:
    return (
        "Send a message for the admin. I will forward it.\n"
        "After the admin taps Reply, this becomes a continuous chat.\n"
        "You can end it anytime with /endchat."
    )

def pair_admin_user(app: Application, admin_id: int, user_id: int) -> None:
    """Create bidirectional pairing for continuous chat."""
    pairs = app.bot_data.setdefault("contact_pairs", {"user_to_admin": {}, "admin_to_user": {}})
    pairs["user_to_admin"][user_id] = admin_id
    pairs["admin_to_user"][admin_id] = user_id

def unpair_admin_user(app: Application, admin_id: Optional[int] = None, user_id: Optional[int] = None) -> None:
    pairs = app.bot_data.setdefault("contact_pairs", {"user_to_admin": {}, "admin_to_user": {}})
    if admin_id is not None:
        uid = pairs["admin_to_user"].pop(admin_id, None)
        if uid is not None:
            pairs["user_to_admin"].pop(uid, None)
    if user_id is not None:
        aid = pairs["user_to_admin"].pop(user_id, None)
        if aid is not None:
            pairs["admin_to_user"].pop(aid, None)

def get_paired(app: Application, admin_id: Optional[int] = None, user_id: Optional[int] = None) -> Optional[int]:
    pairs = app.bot_data.setdefault("contact_pairs", {"user_to_admin": {}, "admin_to_user": {}})
    if admin_id is not None:
        return pairs["admin_to_user"].get(admin_id)
    if user_id is not None:
        return pairs["user_to_admin"].get(user_id)
    return None

# ======================================================================
# Public commands
# ======================================================================
async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Your Telegram ID: <code>{update.effective_user.id}</code>",
        parse_mode=ParseMode.HTML,
    )

async def sudo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Elevate current user to admin if secret matches (set ADMIN_ELEVATE_SECRET in env)."""
    if not context.args:
        await update.message.reply_text("Usage: <code>/sudo &lt;secret&gt;</code>", parse_mode=ParseMode.HTML); return
    secret = " ".join(context.args).strip()
    if not ADMIN_ELEVATE_SECRET:
        await update.message.reply_text("Admin elevate secret is not configured."); return
    if secret != ADMIN_ELEVATE_SECRET:
        await update.message.reply_text("Invalid secret."); return
    with get_session() as db:
        u = get_or_create_user_by_tid(db, update.effective_user.id)
        setattr(u, "is_admin", True)
        db.commit()
    await update.message.reply_text("✅ You are now an admin. Use /users to verify.")

async def endchat_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_admin_user(uid):
        target = get_paired(context.application, admin_id=uid)
        unpair_admin_user(context.application, admin_id=uid)
        await update.message.reply_text("Chat ended.")
        if target:
            try: await context.bot.send_message(chat_id=target, text="The admin ended the chat.")
            except Exception: pass
    else:
        target_admin = get_paired(context.application, user_id=uid)
        unpair_admin_user(context.application, user_id=uid)
        await update.message.reply_text("Chat ended.")
        if target_admin:
            try: await context.bot.send_message(chat_id=target_admin, text=f"User {uid} ended the chat.")
            except Exception: pass

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as db:
        u = get_or_create_user_by_tid(db, update.effective_user.id)
        if not getattr(u, "trial_start", None):
            setattr(u, "trial_start", datetime.now(timezone.utc))
        if not getattr(u, "trial_end", None):
            setattr(u, "trial_end", getattr(u, "trial_start") + timedelta(days=TRIAL_DAYS))
        expiry = getattr(u, "license_until", None) or getattr(u, "trial_end", None)
        db.commit()

    # start fallback loop on first update if needed
    if context.application and context.application.bot_data.get("start_fallback_on_first_update"):
        await _ensure_fallback_running(context.application)
        context.application.bot_data.pop("start_fallback_on_first_update", None)

    await update.effective_chat.send_message(
        welcome_text(expiry), parse_mode=ParseMode.HTML,
        reply_markup=main_menu_kb(is_admin=is_admin_user(update.effective_user.id)),
    )
    await update.effective_chat.send_message(features_text(), parse_mode=ParseMode.HTML)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(
        HELP_EN + help_footer(STATS_WINDOW_HOURS),
        parse_mode=ParseMode.HTML, disable_web_page_preview=True,
    )

async def addkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Add keywords separated by commas. Example:\n<code>/addkeyword logo, lighting</code>",
            parse_mode=ParseMode.HTML,
        ); return
    raw = " ".join(context.args)
    await _add_keywords_flow(update, context, raw)

async def keywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as db:
        u = get_or_create_user_by_tid(db, update.effective_user.id)
        current = list_user_keywords(db, u.id) or []
    await update.message.reply_text(
        "<b>Keywords</b>\n• " + (", ".join(current) if current else "—") +
        "\n\nAdd: <code>/addkeyword logo, lighting</code>\nRemove (not implemented in this build: use Add again to expand)",
        parse_mode=ParseMode.HTML,
    )

async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as db:
        u = get_or_create_user_by_tid(db, update.effective_user.id)
        kws = list_user_keywords(db, u.id)
        trial_start = getattr(u, "trial_start", None)
        trial_end = getattr(u, "trial_end", None)
        license_until = getattr(u, "license_until", None)
    await update.message.reply_text(
        settings_text(
            keywords=kws, countries=getattr(u, "countries", "ALL"),
            proposal_template=getattr(u, "proposal_template", None),
            trial_start=trial_start, trial_end=trial_end, license_until=license_until,
            active=bool(getattr(u, "is_active", True)), blocked=bool(getattr(u, "is_blocked", False)),
        ),
        parse_mode=ParseMode.HTML, disable_web_page_preview=True,
    )

async def selftest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    job_text = (
        "<b>Email Signature from Existing Logo</b>\n"
        "<b>Budget:</b> 10.0–30.0 USD\n"
        "<b>Source:</b> Freelancer\n"
        "<b>Match:</b> logo\n"
        "✏️ Please create an editable version of the email signature based on the provided logo.\n"
    )
    proposal_url = "https://www.freelancer.com/get/apstld?f=give&dl=https://www.freelancer.com/projects/sample"
    original_url = proposal_url
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📄 Proposal", url=proposal_url),
             InlineKeyboardButton("🔗 Original", url=original_url)],
            [InlineKeyboardButton("⭐ Save", callback_data="job:save"),
             InlineKeyboardButton("🗑️ Delete", callback_data="job:delete")],
        ]
    )
    await update.effective_chat.send_message(job_text, parse_mode=ParseMode.HTML, reply_markup=kb)

# ======================================================================
# Admin commands
# ======================================================================
async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        await update.message.reply_text("You are not an admin. If you should be, use /sudo <secret>.")
        return
    with get_session() as db:
        rows = db.query(User).order_by(User.id.desc()).limit(200).all()
    lines = ["<b>Users</b>"]
    for u in rows:
        kw_count = len(u.keywords or [])
        trial = getattr(u, "trial_end", None)
        lic = getattr(u, "license_until", None)
        active = "✅" if getattr(u, "is_active", True) else "❌"
        blocked = "✅" if getattr(u, "is_blocked", False) else "❌"
        lines.append(
            f"• <a href=\"tg://user?id={u.telegram_id}\">{u.telegram_id}</a> — "
            f"kw:{kw_count} | trial:{trial} | lic:{lic} | A:{active} B:{blocked}"
        )
    await update.effective_chat.send_message("\n".join(lines), parse_mode=ParseMode.HTML)

async def grant_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        return
    if len(context.args) < 2:
        await update.effective_chat.send_message("Usage: /grant <telegram_id> <days>"); return
    tg_id = int(context.args[0]); days = int(context.args[1])
    until = datetime.now(timezone.utc) + timedelta(days=days)
    with get_session() as db:
        u = db.query(User).filter(User.telegram_id == tg_id).first()
        if not u:
            await update.effective_chat.send_message("User not found."); return
        setattr(u, "license_until", until); db.commit()
    await update.effective_chat.send_message(f"✅ Granted until {until.isoformat()} for {tg_id}.")
    try:
        await context.bot.send_message(chat_id=tg_id, text=f"🔑 Your access is extended until {until.strftime('%Y-%m-%d %H:%M UTC')}.")
    except Exception:
        pass

async def block_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        return
    if not context.args:
        await update.effective_chat.send_message("Usage: /block <telegram_id>"); return
    tg_id = int(context.args[0])
    with get_session() as db:
        u = db.query(User).filter(User.telegram_id == tg_id).first()
        if not u: await update.effective_chat.send_message("User not found."); return
        setattr(u, "is_blocked", True); db.commit()
    await update.effective_chat.send_message(f"⛔ Blocked {tg_id}.")

async def unblock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        return
    if not context.args:
        await update.effective_chat.send_message("Usage: /unblock <telegram_id>"); return
    tg_id = int(context.args[0])
    with get_session() as db:
        u = db.query(User).filter(User.telegram_id == tg_id).first()
        if not u: await update.effective_chat.send_message("User not found."); return
        setattr(u, "is_blocked", False); db.commit()
    await update.effective_chat.send_message(f"✅ Unblocked {tg_id}.")

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        return
    if not context.args:
        await update.effective_chat.send_message("Usage: /broadcast <text>"); return
    text = " ".join(context.args)
    with get_session() as db:
        users = db.query(User).filter(getattr(User, "is_active") == True, getattr(User, "is_blocked") == False).all()  # noqa: E712
    sent = 0
    for u in users:
        try:
            await context.bot.send_message(chat_id=u.telegram_id, text=text, parse_mode=ParseMode.HTML)
            sent += 1
        except Exception:
            pass
    await update.effective_chat.send_message(f"📣 Broadcast sent to {sent} users.")

async def feedstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        return
    try:
        stats = get_platform_stats(STATS_WINDOW_HOURS) or {}
    except Exception as e:
        await update.effective_chat.send_message(f"Feed status unavailable: {e}"); return
    if not stats:
        await update.effective_chat.send_message(f"No events in the last {STATS_WINDOW_HOURS} hours."); return
    lines = [f"📊 Feed status (last {STATS_WINDOW_HOURS}h):"]
    for src, cnt in stats.items():
        lines.append(f"• {src}: {cnt}")
    await update.effective_chat.send_message("\n".join(lines))

# Add alias /feetstatus (common typo)
async def feetstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await feedstatus_cmd(update, context)

# ======================================================================
# Contact flow (handlers)
# ======================================================================
async def contact_start_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["awaiting_contact"] = True
    await update.callback_query.message.reply_text(user_contact_hint())
    await update.callback_query.answer()

async def incoming_message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Skip if command
    if not update.message or not update.message.text or update.message.text.startswith("/"):
        return
    app = context.application
    uid = update.effective_user.id
    text = update.message.text.strip()

    # If flagged, start fallback scheduler on first incoming message
    if app and app.bot_data.get("start_fallback_on_first_update"):
        await _ensure_fallback_running(app)
        app.bot_data.pop("start_fallback_on_first_update", None)

    # 1) Add-keywords inline mode (after pressing Add Keywords button)
    if context.user_data.pop("awaiting_keywords", False):
        await _add_keywords_flow(update, context, text)
        return

    # 2) Continuous chat routing
    # a) If admin is paired → send to paired user
    if is_admin_user(uid):
        target_user = get_paired(app, admin_id=uid)
        if target_user:
            try:
                await context.bot.send_message(chat_id=target_user, text=f"💬 Admin: {text}")
                # mirror ack optional; avoid clutter
            except Exception:
                await update.message.reply_text("Failed to deliver.")
            return
        # If not paired, ignore (or you can add logic to start new)

    # b) If user is paired → send only to its admin
    target_admin = get_paired(app, user_id=uid)
    if target_admin:
        try:
            await context.bot.send_message(chat_id=target_admin, text=f"✉️ From {uid}:\n\n{text}",
                                           reply_markup=admin_contact_kb(uid))
        except Exception:
            pass
        return

    # c) No pair yet → forward to all admins
    admins = all_admin_ids()
    if not admins:
        await update.message.reply_text("No admin is available at the moment."); return
    for aid in admins:
        try:
            await context.bot.send_message(
                chat_id=aid,
                text=f"✉️ <b>New message from user</b>\nID: <code>{uid}</code>\n\n{text}",
                parse_mode=ParseMode.HTML,
                reply_markup=admin_contact_kb(uid),
            )
        except Exception:
            pass
    await update.message.reply_text("Thanks! Your message was forwarded to the admin 👌")

async def admin_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin_user(q.from_user.id):
        await q.answer("Not allowed", show_alert=True); return
    data = (q.data or "")
    parts = data.split(":")  # adm:reply:<uid> | adm:grant:<uid>:<days> | adm:decline:<uid>
    if len(parts) < 3 or parts[0] != "adm":
        await q.answer(); return
    action = parts[1]; target = int(parts[2])

    if action == "reply":
        pair_admin_user(context.application, q.from_user.id, target)
        await q.message.reply_text(
            f"Replying to <code>{target}</code>. Type your messages. Use /endchat to stop.",
            parse_mode=ParseMode.HTML
        )
        await q.answer(); return

    if action == "decline":
        unpair_admin_user(context.application, user_id=target)
        try:
            await context.bot.send_message(chat_id=target, text="Your message was received. The admin declined to reply.")
        except Exception:
            pass
        await q.answer("Declined"); return

    if action == "grant":
        days = int(parts[3]) if len(parts) >= 4 else 30
        until = datetime.now(timezone.utc) + timedelta(days=days)
        with get_session() as db:
            u = db.query(User).filter(User.telegram_id == target).first()
            if u:
                setattr(u, "license_until", until); db.commit()
        try:
            await context.bot.send_message(chat_id=target, text=f"🔑 Your access is extended until {until.strftime('%Y-%m-%d %H:%M UTC')}.")
        except Exception:
            pass
        await q.answer(f"Granted +{days}d"); return

    await q.answer()

# ======================================================================
# Keywords flow (shared)
# ======================================================================
async def _add_keywords_flow(update: Update, context: ContextTypes.DEFAULT_TYPE, raw_text: str):
    kws = parse_keywords_input(raw_text)
    if not kws:
        await update.effective_chat.send_message("No valid keywords were provided.", parse_mode=ParseMode.HTML)
        return
    with get_session() as db:
        u = get_or_create_user_by_tid(db, update.effective_user.id)
        inserted = add_keywords_safe(db, u.id, kws)
        current = list_user_keywords(db, u.id) or []
    if inserted > 0:
        msg = f"✅ Added {inserted} new keyword(s)."
    else:
        msg = "ℹ️ Those keywords already exist (no changes)."
    await update.effective_chat.send_message(
        msg + "\n\nCurrent keywords:\n• " + (", ".join(current) if current else "—"),
        parse_mode=ParseMode.HTML,
    )

# ======================================================================
# Expiry reminders (scheduler)
# ======================================================================
async def notify_expiring_job(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(timezone.utc)
    soon = now + timedelta(hours=24)
    with get_session() as db:
        users = db.query(User).filter(getattr(User, "is_active") == True, getattr(User, "is_blocked") == False).all()  # noqa: E712
    for u in users:
        expiry = getattr(u, "license_until", None) or getattr(u, "trial_end", None)
        if not expiry:
            continue
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if now < expiry <= soon:
            try:
                left = expiry - now
                hours_left = int(left.total_seconds() // 3600)
                await context.bot.send_message(
                    chat_id=u.telegram_id,
                    text=f"⏰ Reminder: your access expires in about {hours_left} hours (on {expiry.strftime('%Y-%m-%d %H:%M UTC')}).",
                )
            except Exception:
                pass

async def _background_expiry_loop(app: Application):
    await asyncio.sleep(5)  # give app time to start
    while True:
        try:
            ctx = SimpleNamespace(bot=app.bot)
            await notify_expiring_job(ctx)  # type: ignore[arg-type]
        except Exception as e:
            log.exception("expiry loop error: %s", e)
        await asyncio.sleep(3600)

async def _ensure_fallback_running(app: Application):
    if app.bot_data.get("expiry_task"):
        return
    try:
        app.bot_data["expiry_task"] = asyncio.get_event_loop().create_task(_background_expiry_loop(app))
        log.info("Fallback expiry loop started (immediate).")
    except Exception as e:
        log.warning("Could not start fallback loop immediately: %s", e)

# ======================================================================
# Menu callbacks
# ======================================================================
async def menu_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = (q.data or "").strip()

    if data == "act:addkw":
        context.user_data["awaiting_keywords"] = True
        await q.message.reply_text(
            "Type keywords (comma-separated). Example:\n<code>logo, lighting</code>",
            parse_mode=ParseMode.HTML,
        ); await q.answer(); return

    if data == "act:settings":
        with get_session() as db:
            u = get_or_create_user_by_tid(db, q.from_user.id); kws = list_user_keywords(db, u.id)
        txt = settings_text(kws, getattr(u, "countries", "ALL"), getattr(u, "proposal_template", None),
                            getattr(u, "trial_start", None), getattr(u, "trial_end", None),
                            getattr(u, "license_until", None), bool(getattr(u, "is_active", True)),
                            bool(getattr(u, "is_blocked", False)))
        await q.message.reply_text(txt, parse_mode=ParseMode.HTML, disable_web_page_preview=True); await q.answer(); return

    if data == "act:help":
        await q.message.reply_text(HELP_EN + help_footer(STATS_WINDOW_HOURS),
                                   parse_mode=ParseMode.HTML, disable_web_page_preview=True); await q.answer(); return

    if data == "act:saved":
        await q.message.reply_text("💾 Saved (coming soon)."); await q.answer(); return

    if data == "act:contact":
        context.user_data["awaiting_contact"] = True
        await q.message.reply_text(user_contact_hint()); await q.answer(); return

    if data == "act:admin":
        if not is_admin_user(q.from_user.id):
            await q.answer("Not allowed", show_alert=True); return
        await q.message.reply_text(
            "<b>Admin panel</b>\n"
            "/users — list users\n"
            "/grant <id> <days>\n"
            "/block <id> / /unblock <id>\n"
            "/broadcast <text>\n"
            "/feedstatus — per-platform stats\n"
            "/endchat — end current chat pairing",
            parse_mode=ParseMode.HTML,
        )
        await q.answer(); return

    await q.answer()

# ======================================================================
# App factory (safe scheduler init)
# ======================================================================
def build_application() -> Application:
    ensure_schema()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Public commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("whoami", whoami_cmd))
    app.add_handler(CommandHandler("sudo", sudo_cmd))       # elevate to admin with secret
    app.add_handler(CommandHandler("endchat", endchat_cmd)) # end continuous chat
    app.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app.add_handler(CommandHandler("keywords", keywords_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))
    app.add_handler(CommandHandler("selftest", selftest_cmd))

    # Admin commands
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CommandHandler("grant", grant_cmd))
    app.add_handler(CommandHandler("block", block_cmd))
    app.add_handler(CommandHandler("unblock", unblock_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("feedstatus", feedstatus_cmd))
    app.add_handler(CommandHandler("feetstatus", feetstatus_cmd))  # alias

    # Menu & admin actions
    app.add_handler(CallbackQueryHandler(menu_action_cb, pattern=r"^act:(addkw|settings|help|saved|contact|admin)$"))
    app.add_handler(CallbackQueryHandler(admin_action_cb, pattern=r"^adm:(reply|decline|grant):"))

    # Plain text router (contact + inline add-keywords)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, incoming_message_router))

    # ---- Scheduler: try JobQueue; else robust fallback ----
    used_jobqueue = False
    try:
        if JobQueue is not None:
            jq = app.job_queue
            if jq is None:
                jq = JobQueue()
                jq.set_application(app)
            jq.run_repeating(notify_expiring_job, interval=3600, first=60)  # type: ignore[arg-type]
            used_jobqueue = True
            log.info("Scheduler: JobQueue")
    except Exception as e:
        log.warning("JobQueue unavailable (%s). Using fallback.", e)

    if not used_jobqueue:
        # Try to start immediately, else defer to first update
        try:
            app.bot_data["expiry_task"] = asyncio.get_event_loop().create_task(_background_expiry_loop(app))
            log.info("Scheduler: fallback loop (started immediately)")
        except Exception:
            app.bot_data["start_fallback_on_first_update"] = True
            log.info("Scheduler: fallback loop (will start on first update)")

    log.info("Handlers ready: public, admin, contact, keywords, scheduler=%s", "jobqueue" if used_jobqueue else "fallback")
    return app
