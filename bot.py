import os, logging, asyncio
from datetime import datetime, timedelta
from typing import Optional, List
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, Application,
    CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
from sqlalchemy import text
from db import get_session, get_or_create_user_by_tid
from db_keywords import list_keywords, add_keywords, delete_keywords, clear_keywords
from db_events import ensure_feed_events_schema, record_event
from config import ADMIN_IDS, TRIAL_DAYS

# =========================================================
# Logger setup
# =========================================================
log = logging.getLogger("bot")
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is required")

# =========================================================
# Helpers & Converters
# =========================================================
FX = {"EUR": 1.08, "GBP": 1.27, "AUD": 0.65, "CAD": 0.73, "USD": 1.0}
def to_usd(amount: float, cur: str) -> str:
    if not amount or not cur: return ""
    rate = FX.get(cur.upper(), 1)
    if rate == 1: return f"{amount:.2f} USD"
    return f"{amount:.2f} {cur.upper()} (${amount*rate:.2f} USD)"

def is_admin_user(tid: int) -> bool:
    try:
        return tid in set(int(x) for x in (ADMIN_IDS or []))
    except Exception:
        return False

def all_admin_ids():
    return set(int(x) for x in (ADMIN_IDS or []))

# =========================================================
# Layouts / Menus
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

def admin_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Users", callback_data="admin:users"),
         InlineKeyboardButton("📢 Broadcast", callback_data="admin:broadcast")],
        [InlineKeyboardButton("📊 Feed Status", callback_data="admin:feedstatus"),
         InlineKeyboardButton("🗝 Grant License", callback_data="admin:grant")],
        [InlineKeyboardButton("🚫 Block / ✅ Unblock", callback_data="admin:block")]
    ])

def welcome_text(expiry: Optional[datetime]) -> str:
    extra = f"\nFree trial ends: {expiry.strftime('%Y-%m-%d %H:%M UTC')}" if expiry else ""
    return (
        "<b>👋 Welcome to Freelancer Alert Bot!</b>\n\n"
        "🎁 You have a 10-day free trial.\n"
        "Receive instant freelance jobs from top platforms like Freelancer, PeoplePerHour, Malt, Guru, Workana and more."
        f"{extra}\n\n"
        "Use /help for instructions."
    )

HELP_FULL = (
    "🧭 <b>Help / How it works</b>\n\n"
    "1️⃣ Add keywords with <code>/addkeyword logo, python, lighting</code>\n"
    "2️⃣ Adjust countries via <code>/setcountry US,UK</code> or ALL\n"
    "3️⃣ Save a proposal template with <code>/setproposal</code>\n\n"
    "When a job appears:\n"
    "⭐ Save it\n🗑 Delete it\n📄 Proposal → affiliate link\n🔗 Original → same job\n\n"
    "Use /mysettings to review setup.\n"
    "Use /selftest for test jobs.\n\n"
    "Admin commands: /users /grant /block /unblock /broadcast /feedstatus"
)

# =========================================================
# /start and /help
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
        welcome_text(expiry),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_kb(is_admin=is_admin_user(update.effective_user.id))
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(HELP_FULL, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

# =========================================================
# Keywords management
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
# Selftest (restored full dual-platform simulation)
# =========================================================
async def selftest_cmd(update, context):
    ensure_feed_events_schema()
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        now = datetime.utcnow()
        jobs = [
            dict(platform="Freelancer", title="Logo Design", budget_amount=50, budget_currency="EUR",
                 affiliate_url="https://freelancer.com", created_at=now - timedelta(minutes=5)),
            dict(platform="PeoplePerHour", title="WordPress Landing Page", budget_amount=120, budget_currency="USD",
                 affiliate_url="https://peopleperhour.com", created_at=now - timedelta(minutes=8)),
        ]
        for j in jobs:
            record_event(j["platform"], j["title"], j["title"], j["affiliate_url"],
                         j["affiliate_url"], j["budget_amount"], j["budget_currency"],
                         j["budget_amount"], j["created_at"], f"{j['platform']}-{j['title']}")
        s.commit()
    for j in jobs:
        budget_txt = to_usd(j["budget_amount"], j["budget_currency"])
        msg = (
            f"<b>{j['title']}</b>\n"
            f"💰 Budget: {budget_txt}\n"
            f"🌍 Platform: {j['platform']}\n"
            f"⏰ Posted: {j['created_at'].strftime('%H:%M:%S UTC')}"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 Proposal", url=j["affiliate_url"]),
             InlineKeyboardButton("🔗 Original", url=j["affiliate_url"])],
            [InlineKeyboardButton("⭐ Save", callback_data=f"save:{j['platform']}"),
             InlineKeyboardButton("🗑 Delete", callback_data=f"delete:{j['platform']}")]
        ])
        await update.effective_chat.send_message(msg, parse_mode=ParseMode.HTML, reply_markup=kb)
    await update.effective_chat.send_message("✅ Self-Test completed — 2 sample jobs posted.")

# =========================================================
# Contact + Chat reply system
# =========================================================
active_contact = {}

async def contact_cmd(update, context):
    uid = update.effective_user.id
    active_contact[uid] = True
    await update.effective_chat.send_message(
        "📩 Send a message to admin below. Type /cancel to stop chatting.",
        parse_mode=ParseMode.HTML
    )

async def message_router(update, context):
    uid = update.effective_user.id
    txt = update.message.text
    if not txt: return
    # Admin reply
    if is_admin_user(uid) and txt.startswith("/reply"):
        parts = txt.split(maxsplit=2)
        if len(parts) < 3:
            await update.message.reply_text("Usage: /reply <user_id> <message>")
            return
        to_id = int(parts[1]); msg = parts[2]
        await context.bot.send_message(to_id, f"💬 <b>Admin:</b> {msg}", parse_mode=ParseMode.HTML)
        await update.message.reply_text("✅ Reply sent.")
        return
    # Regular user sends message
    if active_contact.get(uid):
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
                f"📨 <b>New contact message</b>\nUser ID: {uid}\n\n{txt}",
                parse_mode=ParseMode.HTML,
                reply_markup=kb
            )
        await update.message.reply_text("✅ Message sent to admin.")
        active_contact[uid] = False
# =========================================================
# FeedStatus + Saved + Users + Menu + Build Application
# =========================================================
async def feedstatus_cmd(update, context):
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
    txt = "<b>📊 Feed Status (24h)</b>\n" + "\n".join(
        [f"• {r['platform']}: {r['cnt']} jobs, last {r['last']:%Y-%m-%d %H:%M}" for r in rows]
    )
    await update.effective_chat.send_message(txt, parse_mode=ParseMode.HTML)

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

async def users_cmd(update, context):
    with get_session() as s:
        rows = s.execute(text("""
            SELECT telegram_id, username, is_active, is_blocked, trial_end, license_until
            FROM "user" ORDER BY id DESC LIMIT 20
        """)).fetchall()
    if not rows:
        await update.effective_chat.send_message("No users found.")
        return
    msg = "\n".join([
        f"{r['telegram_id']} | @{r['username'] or '-'} | Active:{'✅' if r['is_active'] else '❌'} | "
        f"Blocked:{'✅' if r['is_blocked'] else '❌'} | Trial:{r['trial_end']:%Y-%m-%d} | License:{r['license_until'] or '—'}"
        for r in rows
    ])
    await update.effective_chat.send_message(f"<b>👥 Users</b>\n\n{msg}", parse_mode=ParseMode.HTML)

# =========================================================
# Callbacks / Menu actions
# =========================================================
async def save_action_cb(update, context):
    await update.callback_query.answer("⭐ Saved (demo)")

async def delete_action_cb(update, context):
    await update.callback_query.answer("🗑 Deleted (demo)")

async def menu_action_cb(update, context):
    q = update.callback_query; d = q.data; await q.answer()
    if d == "act:addkw": await q.message.chat.send_message("Use /addkeyword logo, python")
    elif d == "act:settings": await q.message.chat.send_message("Use /mysettings")
    elif d == "act:help": await help_cmd(update, context)
    elif d == "act:saved": await saved_cmd(update, context)
    elif d == "act:contact": await contact_cmd(update, context)
    elif d == "act:admin": await q.message.chat.send_message("👑 Admin Panel", reply_markup=admin_menu_kb())
    elif d.startswith("admin:users"): await users_cmd(update, context)
    elif d.startswith("admin:feedstatus"): await feedstatus_cmd(update, context)
    else: await q.message.chat.send_message("❌ Unknown action")

# =========================================================
# Build Application
# =========================================================
def build_application() -> Application:
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("mysettings", help_cmd))
    app.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app.add_handler(CommandHandler("delkeyword", delkeyword_cmd))
    app.add_handler(CommandHandler("clearkeywords", clearkeywords_cmd))
    app.add_handler(CommandHandler("selftest", selftest_cmd))
    app.add_handler(CommandHandler("feedstatus", feedstatus_cmd))
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_router))
    app.add_handler(CallbackQueryHandler(menu_action_cb, pattern=r"^act:"))
    app.add_handler(CallbackQueryHandler(menu_action_cb, pattern=r"^admin:"))
    app.add_handler(CallbackQueryHandler(save_action_cb, pattern=r"^save:"))
    app.add_handler(CallbackQueryHandler(delete_action_cb, pattern=r"^delete:"))
    return app
