# bot.py — full replacement (English-only UX + admin + contact + keywords + expiry reminders)
import os
import logging
import asyncio
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Set

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

# Try import symbol; may exist but instantiation can still fail without extra deps
try:
    from telegram.ext import JobQueue  # type: ignore
except Exception:  # ModuleNotFoundError etc.
    JobQueue = None  # type: ignore

# --- project-local modules ---
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

BOT_TOKEN = (
    os.getenv("TELEGRAM_BOT_TOKEN")
    or os.getenv("BOT_TOKEN")
    or os.getenv("TELEGRAM_TOKEN")
)
if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN env var is required")


# ---------------- Admin helpers ----------------
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


# ---------------- UI ----------------
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
    "<b>1)</b> Add keywords with <code>/addkeyword</code> (comma-separated).\n"
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
        "<b>👑 Admin:</b> /users /grant /block /unblock /broadcast /feedstatus\n"
        "<i>Link previews disabled for clean help.</i>\n"
    )

def welcome_text(expiry: datetime | None) -> str:
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


# ---------------- Keyword helpers ----------------
def parse_keywords_input(raw: str) -> List[str]:
    parts = [p.strip() for chunk in raw.split(",") for p in chunk.split() if p.strip()]
    seen, clean = set(), []
    for p in parts:
        k = p.lower()
        if k not in seen:
            seen.add(k); clean.append(p)
    return clean

def add_keywords_safe(db_session, user_id: int, keywords: List[str]) -> int:
    if not keywords:
        return 0
    inserted = 0
    try:
        res = add_user_keywords(db_session, user_id, keywords)  # try list
        inserted = int(res) if res is not None else 0
        if inserted == 0:
            current = list_user_keywords(db_session, user_id) or []
            inserted = max(0, len(set([*current, *keywords])) - len(current))
    except TypeError:
        try:
            res = add_user_keywords(db_session, user_id, ", ".join(keywords))  # fallback str
            inserted = int(res) if res is not None else 0
            if inserted == 0:
                current = list_user_keywords(db_session, user_id) or []
                inserted = max(0, len(set([*current, *keywords])) - len(current))
        except Exception:
            inserted = 0
    except Exception:
        inserted = 0
    return inserted

def remove_keyword_safe(db_session, user_id: int, keyword: str) -> bool:
    try:
        from db import remove_user_keyword  # optional
        before = list_user_keywords(db_session, user_id) or []
        if keyword in before:
            remove_user_keyword(db_session, user_id, keyword)  # type: ignore
            after = list_user_keywords(db_session, user_id) or []
            return keyword not in after
    except Exception:
        pass
    return False


# ---------------- Contact flow ----------------
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
    return "Send a message for the admin. I'll forward it.\nType your message now (or /cancel)."


# ---------------- Public commands ----------------
async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Your Telegram ID: <code>{update.effective_user.id}</code>",
        parse_mode=ParseMode.HTML,
    )

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as db:
        u = get_or_create_user_by_tid(db, update.effective_user.id)
        if not getattr(u, "trial_start", None):
            setattr(u, "trial_start", datetime.now(timezone.utc))
        if not getattr(u, "trial_end", None):
            setattr(u, "trial_end", getattr(u, "trial_start") + timedelta(days=TRIAL_DAYS))
        expiry = getattr(u, "license_until", None) or getattr(u, "trial_end", None)
        db.commit()
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
    kws = parse_keywords_input(" ".join(context.args))
    if not kws:
        await update.message.reply_text("No valid keywords were provided.", parse_mode=ParseMode.HTML); return
    with get_session() as db:
        u = get_or_create_user_by_tid(db, update.effective_user.id)
        inserted = add_keywords_safe(db, u.id, kws)
        current = list_user_keywords(db, u.id) or []
    await update.message.reply_text(
        f"✅ Added {inserted} new keyword(s).\n\nCurrent keywords:\n• " + (", ".join(current) if current else "—"),
        parse_mode=ParseMode.HTML,
    )

async def keywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as db:
        u = get_or_create_user_by_tid(db, update.effective_user.id)
        current = list_user_keywords(db, u.id) or []
    await update.message.reply_text(
        "<b>Keywords</b>\n• " + (", ".join(current) if current else "—") +
        "\n\nAdd: <code>/addkeyword logo, lighting</code>\nRemove: <code>/delkeyword logo</code>",
        parse_mode=ParseMode.HTML,
    )

async def delkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: <code>/delkeyword &lt;word&gt;</code>", parse_mode=ParseMode.HTML); return
    word = " ".join(context.args).strip()
    with get_session() as db:
        u = get_or_create_user_by_tid(db, update.effective_user.id)
        ok = remove_keyword_safe(db, u.id, word)
        current = list_user_keywords(db, u.id) or []
    if ok:
        await update.message.reply_text(f"🗑 Removed <b>{word}</b>.\nCurrent: " + (", ".join(current) if current else "—"),
                                        parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("Could not remove it automatically. You can still add with /addkeyword.",
                                        parse_mode=ParseMode.HTML)

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

# ---------------- Admin commands ----------------
async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        return
    with get_session() as db:
        rows = db.query(User).order_by(User.id.desc()).limit(100).all()
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
    stats = get_platform_stats(STATS_WINDOW_HOURS)
    if not stats:
        await update.effective_chat.send_message(f"No events in the last {STATS_WINDOW_HOURS} hours."); return
    lines = [f"📊 Feed status (last {STATS_WINDOW_HOURS}h):"]
    for src, cnt in stats.items():
        lines.append(f"• {src}: {cnt}")
    await update.effective_chat.send_message("\n".join(lines))


# ---------------- Contact routing ----------------
async def contact_start_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["awaiting_contact"] = True
    await update.callback_query.message.reply_text(user_contact_hint())
    await update.callback_query.answer()

async def incoming_message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not update.message or not update.message.text or update.message.text.startswith("/"):
        return
    text = update.message.text.strip()

    # Admin replying?
    pending: Dict[int, int] = context.bot_data.setdefault("pending_replies", {})
    if is_admin_user(uid) and uid in pending:
        target_id = pending.pop(uid, None)
        if target_id:
            try:
                await context.bot.send_message(chat_id=target_id, text=f"💬 Admin: {text}")
                await update.message.reply_text("✅ Sent.")
            except Exception:
                await update.message.reply_text("Failed to deliver.")
        return

    # Regular user → forward to admins
    if is_admin_user(uid):
        return
    for aid in all_admin_ids():
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
    parts = (q.data or "").split(":")  # adm:reply:<uid>  | adm:grant:<uid>:<days> | adm:decline:<uid>
    if len(parts) < 3 or parts[0] != "adm":
        await q.answer(); return
    action, target = parts[1], int(parts[2])

    if action == "reply":
        context.bot_data.setdefault("pending_replies", {})[q.from_user.id] = target
        await q.message.reply_text(f"Reply to <code>{target}</code>: type your message now.", parse_mode=ParseMode.HTML)
        await q.answer(); return

    if action == "decline":
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


# ---------------- Expiry reminders ----------------
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


# ---------------- Menu callbacks ----------------
async def menu_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = (q.data or "").strip()

    if data == "act:addkw":
        await q.message.reply_text(
            "Add keywords (comma-separated). Example:\n<code>/addkeyword logo, lighting</code>",
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
            "/feedstatus — per-platform stats",
            parse_mode=ParseMode.HTML,
        ); await q.answer(); return

    await q.answer()


# ---------------- App factory (safe JobQueue init) ----------------
def build_application() -> Application:
    ensure_schema()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Public commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("whoami", whoami_cmd))
    app.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app.add_handler(CommandHandler("keywords", keywords_cmd))
    app.add_handler(CommandHandler("delkeyword", delkeyword_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))
    app.add_handler(CommandHandler("selftest", selftest_cmd))

    # Admin commands
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CommandHandler("grant", grant_cmd))
    app.add_handler(CommandHandler("block", block_cmd))
    app.add_handler(CommandHandler("unblock", unblock_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("feedstatus", feedstatus_cmd))

    # Menu & admin actions
    app.add_handler(CallbackQueryHandler(menu_action_cb, pattern=r"^act:(addkw|settings|help|saved|contact|admin)$"))
    app.add_handler(CallbackQueryHandler(admin_action_cb, pattern=r"^adm:(reply|decline|grant):"))

    # Plain text router (for contact and admin replies)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, incoming_message_router))

    # --- Scheduling: try JobQueue; if ANY exception → fallback loop ---
    def _start_fallback_loop(_: Application) -> None:
        # run background loop after init
        app.bot_data["expiry_task"] = asyncio.create_task(_background_expiry_loop(app))

    used_jobqueue = False
    try:
        if JobQueue is not None:
            jq = app.job_queue
            if jq is None:
                jq = JobQueue()
                jq.set_application(app)
            jq.run_repeating(notify_expiring_job, interval=3600, first=60)  # type: ignore[arg-type]
            used_jobqueue = True
    except Exception as e:
        log.warning("JobQueue unavailable (%s). Using fallback loop.", e)

    if not used_jobqueue:
        # PTB calls post_init callbacks on start
        app.post_init.append(_start_fallback_loop)

    log.info("Handlers ready. Scheduler=%s", "jobqueue" if used_jobqueue else "fallback-loop")
    return app
