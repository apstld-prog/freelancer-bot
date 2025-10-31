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
from config import ADMIN_IDS, TRIAL_DAYS, STATS_WINDOW_HOURS

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
    "  Placeholders: {jobtitle}, {experience}, {stack}, {budgetitem}, {name}\n"
    "4️⃣ When a job arrives you can:\n"
    "⭐ Keep it\n🗑 Delete it\n📄 Proposal → direct affiliate link\n🔗 Original → affiliate wrapped job link\n\n"
    "Use <code>/mysettings</code> to check your filters and proposal.\n"
    "Use <code>/selftest</code> for a test job.\n"
    "Use <code>/platforms GR</code> for local platforms.\n\n"
    "🌍 <b>Platforms monitored:</b>\n"
    "• Global: Freelancer.com (affiliate), PeoplePerHour, Malt, Workana, Guru, 99designs, Toptal, Codeable, "
    "YunoJuno, Worksome, twago, freelancermap\n"
    "• Greece: JobFind.gr, Skywalker.gr, Kariera.gr\n\n"
    "👑 <b>Admin commands:</b>\n"
    "<code>/users</code> — list users\n"
    "<code>/grant &lt;telegram_id&gt; &lt;days&gt;</code> — extend license\n"
    "<code>/block &lt;telegram_id&gt;</code> / <code>/unblock</code>\n"
    "<code>/broadcast &lt;text&gt;</code> — send message to all active\n"
    "<code>/feedstatus</code> — show active feed toggles"
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
    txt = (
        "<b>Email Signature from Existing Logo</b>\n"
        "💰 Budget: 10 – 30 EUR ($10.8 – $32.4 USD)\n"
        "🌍 Source: Freelancer\n"
        "🔎 Match: logo\n"
        "📝 Please duplicate and make an editable version of my existing email signature based on the logo file."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Proposal", url="https://freelancer.com"),
         InlineKeyboardButton("🔗 Original", url="https://freelancer.com")],
        [InlineKeyboardButton("⭐ Save", callback_data="save:test"),
         InlineKeyboardButton("🗑 Delete", callback_data="delete:test")]
    ])
    ensure_feed_events_schema()
    record_event("freelancer")
    record_event("peopleperhour")
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
        await update.effective_chat.send_message("📊 No feed activity in last 24 hours.")
        return
    msg = ["📊 <b>Feed status (last 24 h)</b>:"]
    for r in rows:
        status = "✅ active" if r["cnt"] > 0 else "❌ inactive"
        msg.append(f"• {r['platform']} — {status} ({r['cnt']} jobs, last: {r['last']:%Y-%m-%d %H:%M})")
    await update.effective_chat.send_message("\n".join(msg), parse_mode=ParseMode.HTML)

async def saved_cmd(update, context):
    uid = update.effective_user.id
    with get_session() as s:
        rows = s.execute(text("""
            SELECT je.platform, je.title, je.affiliate_url,
                   je.budget_amount, je.budget_currency, je.created_at
            FROM saved_job sj
            LEFT JOIN job_event je ON je.id=sj.job_id
            WHERE sj.user_id=(SELECT id FROM "user" WHERE telegram_id=:tid)
            ORDER BY sj.saved_at DESC LIMIT 10
        """), {"tid": uid}).fetchall()
    if not rows:
        await update.effective_chat.send_message("💾 You have no saved jobs yet.")
        return
    msg = "<b>💾 Saved Jobs:</b>\n" + "\n\n".join(
        [f"• {r['title']}\n💰 {to_usd(r['budget_amount'], r['budget_currency'])}\n🌍 {r['platform']}\n🔗 <a href='{r['affiliate_url']}'>Open</a>"
         for r in rows]
    )
    await update.effective_chat.send_message(msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
# =========================================================
# Contact Chat / Admin
# =========================================================
user_contact_state = {}

async def contact_cmd(update, context):
    uid = update.effective_user.id
    user_contact_state[uid] = True
    await update.effective_chat.send_message("✉️ Send your message to the admin.\nType /cancel to exit.")

async def message_router(update, context):
    uid = update.effective_user.id
    txt = update.message.text
    if not txt:
        return
    # ADMIN reply logic
    if is_admin_user(uid) and txt.startswith("/reply"):
        parts = txt.split(maxsplit=2)
        if len(parts) < 3:
            await update.message.reply_text("Usage: /reply &lt;user_id&gt; &lt;msg&gt;", parse_mode=ParseMode.HTML)
            return
        to = int(parts[1]); msg = parts[2]
        await context.bot.send_message(to, f"💬 Admin: {msg}")
        await update.message.reply_text("✅ Reply sent.")
        return
    if is_admin_user(uid):
        await update.message.reply_text("ℹ️ Use /reply &lt;user_id&gt; &lt;msg&gt; to respond.")
        return

    # USER → ADMIN
    if user_contact_state.get(uid):
        for admin in all_admin_ids():
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("💬 Reply", callback_data=f"reply:{uid}"),
                 InlineKeyboardButton("❌ Delete", callback_data=f"decline:{uid}")],
                [InlineKeyboardButton("+30d", callback_data=f"grant:{uid}:30"),
                 InlineKeyboardButton("+90d", callback_data=f"grant:{uid}:90"),
                 InlineKeyboardButton("+180d", callback_data=f"grant:{uid}:180"),
                 InlineKeyboardButton("+365d", callback_data=f"grant:{uid}:365")]
            ])
            await context.bot.send_message(
                admin,
                f"📩 <b>New message from user</b>\nID: <a href='tg://user?id={uid}'>{uid}</a>\n\n{txt}",
                parse_mode=ParseMode.HTML,
                reply_markup=kb
            )
        await update.message.reply_text("✅ Message sent to admin.")
        user_contact_state[uid] = False

async def users_cmd(update, context):
    if not is_admin_user(update.effective_user.id):
        await update.effective_chat.send_message("⛔ Not allowed.")
        return
    with get_session() as s:
        rows = s.execute(text("""
            SELECT telegram_id, username, is_active, is_blocked,
                   trial_end, license_until
            FROM "user" ORDER BY id DESC LIMIT 30
        """)).fetchall()
    if not rows:
        await update.effective_chat.send_message("No users found.")
        return
    lines = [f"{r['telegram_id']} | @{r['username'] or '-'} | Active:{'✅' if r['is_active'] else '❌'} | "
             f"Blocked:{'✅' if r['is_blocked'] else '❌'} | Trial ends:{r['trial_end']:%Y-%m-%d} | "
             f"License:{r['license_until'] or '—'}" for r in rows]
    await update.effective_chat.send_message("\n".join(lines))

# =========================================================
# Menu Handler and App Builder
# =========================================================
async def menu_action_cb(update, context):
    q = update.callback_query
    data = q.data
    await q.answer()
    if data == "act:addkw":
        await q.message.chat.send_message("Use /addkeyword &lt;text&gt; to add keywords.", parse_mode=ParseMode.HTML)
    elif data == "act:settings":
        await context.bot.send_message(q.message.chat_id, "⚙️ Use /mysettings to view settings.")
    elif data == "act:help":
        await help_cmd(update, context)
    elif data == "act:saved":
        await saved_cmd(update, context)
    elif data == "act:contact":
        await contact_cmd(update, context)
    elif data == "act:admin":
        await users_cmd(update, context)
    else:
        await q.message.chat.send_message("❌ Unknown action.")

def build_application() -> Application:
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app.add_handler(CommandHandler("delkeyword", delkeyword_cmd))
    app.add_handler(CommandHandler("clearkeywords", clearkeywords_cmd))
    app.add_handler(CommandHandler("selftest", selftest_cmd))
    app.add_handler(CommandHandler("feedstatus", feedstatus_cmd))
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_router))
    app.add_handler(CallbackQueryHandler(menu_action_cb, pattern=r"^act:"))
    return app
