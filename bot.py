import os, logging, asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, Application, CommandHandler,
    CallbackQueryHandler, MessageHandler, ContextTypes, filters
)
from sqlalchemy import text
from db import get_session, get_or_create_user_by_tid
from db_keywords import list_keywords, add_keywords, delete_keywords, clear_keywords
from db_events import ensure_feed_events_schema, record_event
from config import ADMIN_IDS, TRIAL_DAYS

log = logging.getLogger("bot")
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN env var is required")

# =========================================================
# Admin utilities
# =========================================================
def get_db_admin_ids():
    try:
        with get_session() as s:
            ids = [r["telegram_id"] for r in s.execute(text('SELECT telegram_id FROM "user" WHERE is_admin=TRUE')).fetchall()]
        return set(int(x) for x in ids if x)
    except Exception:
        return set()

def all_admin_ids():
    return set(int(x) for x in (ADMIN_IDS or [])) | get_db_admin_ids()

def is_admin_user(tid: int) -> bool:
    return tid in all_admin_ids()

# =========================================================
# Helpers / Conversion
# =========================================================
FX = {"EUR": 1.08, "GBP": 1.27, "AUD": 0.65, "CAD": 0.73, "USD": 1.0}
def to_usd(amount: float, cur: str) -> str:
    if not amount or not cur: return ""
    rate = FX.get(cur.upper(), 1)
    if rate == 1: return f"{amount:.2f} USD"
    return f"{amount:.2f} {cur.upper()} (${amount*rate:.2f} USD)"

# =========================================================
# Menus and text blocks
# =========================================================
def main_menu_kb(is_admin=False):
    kb = [
        [InlineKeyboardButton("➕ Add Keywords", callback_data="act:addkw"),
         InlineKeyboardButton("⚙️ Settings", callback_data="act:settings")],
        [InlineKeyboardButton("🆘 Help", callback_data="act:help"),
         InlineKeyboardButton("💾 Saved", callback_data="act:saved")],
        [InlineKeyboardButton("📨 Contact", callback_data="act:contact")]
    ]
    if is_admin:
        kb.append([InlineKeyboardButton("🔥 Admin", callback_data="act:admin")])
    return InlineKeyboardMarkup(kb)

def welcome_text(expiry: Optional[datetime]) -> str:
    extra = f"\nFree trial ends: {expiry.strftime('%Y-%m-%d %H:%M UTC')}" if expiry else ""
    return ("<b>👋 Welcome to Freelancer Alert Bot!</b>\n\n"
            "🎁 You have a 10-day free trial.\n"
            "The bot finds freelance jobs from top platforms and sends alerts instantly."
            f"\n{extra}\n\nUse /help for instructions.")

HELP_FULL = (
    "🧭 <b>Help / How it works</b>\n\n"
    "1️⃣ Add keywords with <code>/addkeyword python, telegram</code> (English or Greek)\n"
    "2️⃣ Set countries with <code>/setcountry US,UK</code> or <code>ALL</code>\n"
    "3️⃣ Save a proposal template with <code>/setproposal &lt;text&gt;</code>\n"
    "   Placeholders: {jobtitle}, {experience}, {stack}, {budgetitem}, {name}\n"
    "4️⃣ When a job arrives you can:\n"
    "⭐ Keep it\n🗑 Delete it\n📄 Proposal → affiliate link\n🔗 Original → same wrapped link\n\n"
    "Use <code>/mysettings</code> to check filters.\n"
    "Use <code>/selftest</code> to test job.\n"
    "Use <code>/platforms GR</code> to view Greek sites.\n\n"
    "🌍 <b>Platforms:</b> Freelancer, PeoplePerHour, Malt, Workana, Guru, 99designs, "
    "Toptal, Codeable, YunoJuno, Worksome, twago, freelancermap\n"
    "🇬🇷 Greece: JobFind.gr, Skywalker.gr, Kariera.gr\n\n"
    "👑 <b>Admin:</b> /users /grant /block /unblock /broadcast /feedstatus"
)

# =========================================================
# /start & /help
# =========================================================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        s.execute('UPDATE "user" SET trial_start=COALESCE(trial_start,NOW()), '
                  'trial_end=COALESCE(trial_end,NOW()+make_interval(days=>%(d)s)) '
                  'WHERE id=%(id)s;', {"id": u.id, "d": TRIAL_DAYS})
        expiry = s.execute(text('SELECT COALESCE(license_until, trial_end) AS exp FROM "user" WHERE id=:i'),
                           {"i": u.id}).fetchone()["exp"]
        s.commit()
    await update.effective_chat.send_message(
        welcome_text(expiry), parse_mode=ParseMode.HTML,
        reply_markup=main_menu_kb(is_admin=is_admin_user(update.effective_user.id))
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(HELP_FULL, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

# =========================================================
# Keywords
# =========================================================
def _parse_keywords(raw: str) -> List[str]:
    parts = [p.strip() for chunk in raw.split(",") for p in chunk.split() if p.strip()]
    seen, out = set(), []
    for p in parts:
        if p.lower() not in seen:
            seen.add(p.lower())
            out.append(p)
    return out

async def addkeyword_cmd(update, context):
    if not context.args:
        await update.message.reply_text("Usage:\n<code>/addkeyword logo, lighting</code>", parse_mode=ParseMode.HTML)
        return
    kws = _parse_keywords(" ".join(context.args))
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        add_keywords(u.id, kws)
    await update.message.reply_text("✅ Keywords added.")

async def delkeyword_cmd(update, context):
    if not context.args:
        await update.message.reply_text("Usage:\n<code>/delkeyword logo</code>", parse_mode=ParseMode.HTML)
        return
    kws = _parse_keywords(" ".join(context.args))
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        delete_keywords(u.id, kws)
    await update.message.reply_text("🗑 Keywords deleted.")

async def clearkeywords_cmd(update, context):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        clear_keywords(u.id)
    await update.message.reply_text("✅ All keywords cleared.")
# =========================================================
# Selftest / Feedstatus / Saved
# =========================================================
async def selftest_cmd(update, context):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        ensure_feed_events_schema()
        record_event("freelancer")
        # Save dummy job for test
        s.execute(text("""
            INSERT INTO saved_job (user_id, event_id, saved_at)
            VALUES (:u, (SELECT MAX(id) FROM job_event), NOW())
        """), {"u": u.id})
        s.commit()
    txt = (
        "<b>Logo Project Test</b>\n"
        "💰 Budget: 50 EUR ($54.00 USD)\n"
        "🌍 Source: Freelancer\n"
        "🔎 Match: logo"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Proposal", url="https://freelancer.com"),
         InlineKeyboardButton("🔗 Original", url="https://freelancer.com")],
        [InlineKeyboardButton("⭐ Save", callback_data="save:test"),
         InlineKeyboardButton("🗑 Delete", callback_data="delete:test")]
    ])
    await update.effective_chat.send_message(txt, parse_mode=ParseMode.HTML, reply_markup=kb)
    await update.effective_chat.send_message("✅ Self-test OK — dummy events recorded.")

async def feedstatus_cmd(update, context):
    ensure_feed_events_schema()
    with get_session() as s:
        rows = s.execute(text("""
            SELECT platform, COUNT(*) AS cnt, MAX(created_at) AS last
            FROM job_event
            WHERE created_at > NOW() - interval '24 hour'
            GROUP BY platform ORDER BY platform
        """)).fetchall()
    if not rows:
        await update.effective_chat.send_message("📊 No feed activity in last 24h.")
        return
    msg = ["📊 <b>Feed status (24h)</b>:"]
    for r in rows:
        msg.append(f"• {r['platform']} — {r['cnt']} jobs, latest: {r['last']:%Y-%m-%d %H:%M}")
    await update.effective_chat.send_message("\n".join(msg), parse_mode=ParseMode.HTML)

async def saved_cmd(update, context):
    uid = update.effective_user.id
    with get_session() as s:
        rows = s.execute(text("""
            SELECT je.platform, je.title, je.affiliate_url,
                   je.budget_amount, je.budget_currency, je.created_at
            FROM saved_job sj
            LEFT JOIN job_event je ON je.id=sj.event_id
            WHERE sj.user_id=(SELECT id FROM "user" WHERE telegram_id=:tid)
            ORDER BY sj.saved_at DESC LIMIT 10
        """), {"tid": uid}).fetchall()
    if not rows:
        await update.effective_chat.send_message("💾 No saved jobs yet.")
        return
    msg = "<b>💾 Saved Jobs:</b>\n" + "\n\n".join(
        [f"• {r['title']}\n💰 {to_usd(r['budget_amount'], r['budget_currency'])}\n🌍 {r['platform']}\n🔗 <a href='{r['affiliate_url']}'>Open</a>"
         for r in rows]
    )
    await update.effective_chat.send_message(msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

# =========================================================
# My Settings
# =========================================================
async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        kws = list_keywords(u.id)
        r = s.execute(text("""
            SELECT countries, proposal_template, trial_start, trial_end, license_until, is_active, is_blocked
            FROM "user" WHERE id=:id
        """), {"id": u.id}).fetchone()
    k = ", ".join(kws) if kws else "(none)"
    c = r["countries"] if r["countries"] else "ALL"
    active = "✅" if r["is_active"] else "❌"
    blocked = "✅" if r["is_blocked"] else "❌"
    txt = (
        f"<b>🛠 Your Settings</b>\n\n"
        f"• Keywords: {k}\n• Countries: {c}\n• Proposal: {'(saved)' if r['proposal_template'] else '(none)'}\n"
        f"• Trial ends: {r['trial_end']:%Y-%m-%d}\n• License: {r['license_until'] or '—'}\n"
        f"• Active: {active}   Blocked: {blocked}\n\n<i>Contact admin for extension.</i>"
    )
    await update.effective_chat.send_message(txt, parse_mode=ParseMode.HTML)

# =========================================================
# Contact / Admin chat
# =========================================================
def admin_contact_kb(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Reply", callback_data=f"adm:reply:{user_id}"),
         InlineKeyboardButton("❌ Decline", callback_data=f"adm:decline:{user_id}")],
        [InlineKeyboardButton("+30d", callback_data=f"adm:grant:{user_id}:30"),
         InlineKeyboardButton("+90d", callback_data=f"adm:grant:{user_id}:90"),
         InlineKeyboardButton("+180d", callback_data=f"adm:grant:{user_id}:180"),
         InlineKeyboardButton("+365d", callback_data=f"adm:grant:{user_id}:365")],
    ])

def pair_admin_user(app: Application, admin_id: int, user_id: int) -> None:
    pairs = app.bot_data.setdefault("contact_pairs", {"user_to_admin": {}, "admin_to_user": {}})
    pairs["user_to_admin"][user_id] = admin_id
    pairs["admin_to_user"][admin_id] = user_id

def get_paired_admin(app: Application, user_id: int) -> Optional[int]:
    return app.bot_data.setdefault("contact_pairs", {"user_to_admin": {}, "admin_to_user": {}})["user_to_admin"].get(user_id)

def get_paired_user(app: Application, admin_id: int) -> Optional[int]:
    return app.bot_data.setdefault("contact_pairs", {"user_to_admin": {}, "admin_to_user": {}})["admin_to_user"].get(admin_id)

def unpair(app: Application, admin_id: Optional[int]=None, user_id: Optional[int]=None):
    pairs = app.bot_data.setdefault("contact_pairs", {"user_to_admin": {}, "admin_to_user": {}})
    if admin_id is not None:
        uid = pairs["admin_to_user"].pop(admin_id, None)
        if uid is not None: pairs["user_to_admin"].pop(uid, None)
    if user_id is not None:
        aid = pairs["user_to_admin"].pop(user_id, None)
        if aid is not None: pairs["admin_to_user"].pop(aid, None)

# =========================================================
# Admin Commands / Menu
# =========================================================
async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        await update.message.reply_text("You are not an admin."); return
    with get_session() as s:
        rows = s.execute(text('SELECT id, telegram_id, trial_end, license_until, is_active, is_blocked FROM "user" ORDER BY id DESC LIMIT 200')).fetchall()
    lines = ["<b>Users</b>"]
    for uid, tid, trial_end, lic, act, blk in rows:
        kwc = count_keywords(uid)
        lines.append(f"• <a href=\"tg://user?id={tid}\">{tid}</a> — kw:{kwc} | trial:{trial_end} | lic:{lic} | A:{'✅' if act else '❌'} B:{'✅' if blk else '❌'}")
    await update.effective_chat.send_message("\n".join(lines), parse_mode=ParseMode.HTML)

async def feedstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id): return
    try:
        stats = get_platform_stats(STATS_WINDOW_HOURS) or {}
    except Exception as e:
        await update.effective_chat.send_message(f"Feed status unavailable: {e}"); return
    if not stats:
        await update.effective_chat.send_message(f"No events in the last {STATS_WINDOW_HOURS} hours."); return
    await update.effective_chat.send_message("📊 Feed status (last %dh):\n%s" % (
        STATS_WINDOW_HOURS, "\n".join([f"• {k}: {v}" for k,v in stats.items()])
    ))

async def feetstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await feedstatus_cmd(update, context)

async def grant_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id): return
    if len(context.args) < 2:
        await update.effective_chat.send_message("Usage: /grant <id> <days>"); return
    tid = int(context.args[0]); days = int(context.args[1])
    until = datetime.now(timezone.utc) + timedelta(days=days)
    with get_session() as s:
        s.execute(text('UPDATE "user" SET license_until=:dt WHERE telegram_id=:tid'), {"dt": until, "tid": tid}); s.commit()
    await update.effective_chat.send_message(f"✅ Granted until {until.isoformat()} for {tid}.")
    try: await context.bot.send_message(chat_id=tid, text=f"🔑 Your access is extended until {until.strftime('%Y-%m-%d %H:%M UTC')}.")
    except Exception: pass

async def block_cmd(update: Update, Context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id): return
    if not update.message or not update.message.text: return
    parts = update.message.text.split()
    if len(parts) < 2:
        await update.effective_chat.send_message("Usage: /block <id>"); return
    tid = int(parts[1])
    with get_session() as s:
        s.execute(text('UPDATE "user" SET is_blocked=TRUE WHERE telegram_id=:tid'), {"tid": tid}); s.commit()
    await update.effective_chat.send_message(f"⛔ Blocked {tid}.")

async def unblock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id): return
    if not update.message or not update.message.text: return
    parts = update.message.text.split()
    if len(parts) < 2:
        await update.effective_chat.send_message("Usage: /unblock <id>"); return
    tid = int(parts[1])
    with get_session() as s:
        s.execute(text('UPDATE "user" SET is_blocked=FALSE WHERE telegram_id=:tid'), {"tid": tid}); s.commit()
    await update.effective_chat.send_message(f"✅ Unblocked {tid}.")

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id): return
    if not context.args: await update.effective_chat.send_message("Usage: /broadcast <text>"); return
    txt = " ".join(context.args)
    with get_session() as s:
        ids = [r[0] for r in s.execute(text('SELECT telegram_id FROM "user" WHERE is_active=TRUE AND is_blocked=FALSE')).fetchall()]
    for tid in ids:
        try: await context.bot.send_message(chat_id=tid, text=txt, parse_mode=ParseMode.HTML)
        except Exception: pass
    await update.effective_chat.send_message(f"📣 Broadcast sent to {len(ids)} users.")

# =========================================================
# Save/Delete callbacks
# =========================================================
async def save_action_cb(update, context):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("⭐ Saved successfully (dummy).")

async def delete_action_cb(update, context):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("🗑 Deleted (dummy).")

# =========================================================
# Menu Actions
# =========================================================
async def menu_action_cb(update, context):
    q = update.callback_query
    data = q.data
    await q.answer()
    if data == "act:addkw":
        await q.message.chat.send_message("Use /addkeyword <text> to add keywords.", parse_mode=ParseMode.HTML)
    elif data == "act:settings":
        await mysettings_cmd(update, context)
    elif data == "act:help":
        await help_cmd(update, context)
    elif data == "act:saved":
        await saved_cmd(update, context)
    elif data == "act:contact":
        await contact_cmd(update, context)
    elif data == "act:admin":
        await admin_menu_cmd(update, context)
    elif data.startswith("admin:users"):
        await users_cmd(update, context)
    elif data.startswith("admin:feedstatus"):
        await feedstatus_cmd(update, context)
    else:
        await q.message.chat.send_message("❌ Unknown action.")

# ---------- Expiry reminders ----------
async def notify_expiring_job(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(timezone.utc); soon = now + timedelta(hours=24)
    with get_session() as s:
        rows = s.execute(text('SELECT telegram_id, COALESCE(license_until, trial_end) FROM "user" WHERE is_active=TRUE AND is_blocked=FALSE')).fetchall()
    for tid, expiry in rows:
        if not expiry: continue
        if getattr(expiry, "tzinfo", None) is None: expiry = expiry.replace(tzinfo=timezone.utc)
        if now < expiry <= soon:
            try:
                hours_left = int((expiry - now).total_seconds() // 3600)
                await context.bot.send_message(chat_id=tid, text=f"⏰ Reminder: your access expires in about {hours_left} hours (on {expiry.strftime('%Y-%m-%d %H:%M UTC')}).")
            except Exception: pass

async def _background_expiry_loop(app: Application):
    await asyncio.sleep(5)
    while True:
        try:
            ctx = SimpleNamespace(bot=app.bot)
            await notify_expiring_job(ctx)  # type: ignore[arg-type]
        except Exception as e:
            log.exception("expiry loop error: %s", e)
        await asyncio.sleep(3600)

async def _ensure_fallback_running(app: Application):
    if app.bot_data.get("expiry_task"): return
    try:
        app.bot_data["expiry_task"] = asyncio.get_event_loop().create_task(_background_expiry_loop(app))
        log.info("Fallback expiry loop started (immediate).")
    except Exception as e:
        log.warning("Could not start fallback loop immediately: %s", e)

# =========================================================
# Application Builder
# =========================================================
def build_application() -> Application:
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))
    app.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app.add_handler(CommandHandler("delkeyword", delkeyword_cmd))
    app.add_handler(CommandHandler("clearkeywords", clearkeywords_cmd))
    app.add_handler(CommandHandler("selftest", selftest_cmd))
    app.add_handler(CommandHandler("feedstatus", feedstatus_cmd))
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_router))
    app.add_handler(CallbackQueryHandler(menu_action_cb, pattern=r"^act:"))
    app.add_handler(CallbackQueryHandler(save_action_cb, pattern=r"^save:"))
    app.add_handler(CallbackQueryHandler(delete_action_cb, pattern=r"^delete:"))
    app.add_handler(CallbackQueryHandler(menu_action_cb, pattern=r"^admin:"))
    return app
