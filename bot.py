import os, logging, asyncio
from datetime import datetime
from typing import List, Set, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, Application, CommandHandler,
    CallbackQueryHandler, MessageHandler, ContextTypes, filters
)
from sqlalchemy import text
from db import get_session, get_or_create_user_by_tid
from config import ADMIN_IDS, TRIAL_DAYS, STATS_WINDOW_HOURS
from db_events import ensure_feed_events_schema, record_event
from db_keywords import list_keywords, add_keywords, delete_keywords, clear_keywords

log = logging.getLogger("bot")
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN env var is required")

# ---------- Admin helpers ----------
def get_db_admin_ids() -> Set[int]:
    try:
        with get_session() as s:
            ids = [r["telegram_id"] for r in s.execute(text('SELECT telegram_id FROM "user" WHERE is_admin=TRUE')).fetchall()]
        return {int(x) for x in ids if x}
    except Exception:
        return set()

def all_admin_ids() -> Set[int]:
    return set(int(x) for x in (ADMIN_IDS or [])) | get_db_admin_ids()

def is_admin_user(tid: int) -> bool:
    return tid in all_admin_ids()

# ---------- UI ----------
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

HELP_EN = (
    "<b>🧭 Help / How it works</b>\n\n"
    "<b>Keywords</b>\n"
    "• Add: <code>/addkeyword logo, lighting, sales</code>\n"
    "• Remove: <code>/delkeyword logo, sales</code>\n"
    "• Clear all: <code>/clearkeywords</code>\n\n"
    "<b>Other</b>\n"
    "• Set countries: <code>/setcountry US,UK</code> or <code>ALL</code>\n"
    "• Save proposal: <code>/setproposal &lt;text&gt;</code>\n"
    "• Test card: <code>/selftest</code>\n"
)

def help_footer(hours: int) -> str:
    return (
        "\n<b>🛰 Platforms monitored:</b>\n"
        "• Global: Freelancer.com, PeoplePerHour, Malt, Workana, Guru, 99designs, "
        "Toptal, Codeable, YunoJuno, Worksome, twago, freelancermap\n"
        "• Greece: JobFind.gr, Skywalker.gr, Kariera.gr\n\n"
        "<b>👑 Admin:</b> /users /grant /block /unblock /broadcast /feedstatus\n"
    )

def welcome_text(expiry: Optional[datetime]) -> str:
    extra = f"\n<b>Free trial ends:</b> {expiry.strftime('%Y-%m-%d %H:%M UTC')}" if expiry else ""
    return (
        "<b>👋 Welcome to Freelancer Alert Bot!</b>\n\n"
        "🎁 You have a <b>10-day free trial</b>.\n"
        "The bot finds freelance jobs from top platforms and sends alerts instantly."
        f"{extra}\n\nUse /help for instructions.\n"
    )
def settings_text(keywords, countries, proposal_template, trial_start, trial_end, license_until, active, blocked):
    def b(v): return "✅" if v else "❌"
    k = ", ".join(keywords) if keywords else "(none)"
    c = countries or "ALL"
    pt = "(none)" if not proposal_template else "(saved)"
    ts = trial_start.isoformat() if trial_start else "—"
    te = trial_end.isoformat() if trial_end else "—"
    lic = license_until.isoformat() if license_until else "None"
    return (f"<b>🛠 Your Settings</b>\n• Keywords: {k}\n• Countries: {c}\n• Proposal: {pt}\n\n"
            f"Start: {ts}\nTrial ends: {te}\nLicense: {lic}\nActive: {b(active)}  Blocked: {b(blocked)}")

# ---------- /start ----------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        s.execute('UPDATE "user" SET trial_start=COALESCE(trial_start,NOW()), trial_end=COALESCE(trial_end,NOW()+make_interval(days=>%(d)s)) WHERE id=%(id)s;', {"id":u.id,"d":TRIAL_DAYS})
        expiry = s.execute(text('SELECT COALESCE(license_until, trial_end) AS expiry FROM "user" WHERE id=:id'),{"id":u.id}).fetchone()["expiry"]
        s.commit()
    await update.effective_chat.send_message(welcome_text(expiry), parse_mode=ParseMode.HTML, reply_markup=main_menu_kb(is_admin=is_admin_user(update.effective_user.id)))
    await update.effective_chat.send_message(HELP_EN + help_footer(STATS_WINDOW_HOURS), parse_mode=ParseMode.HTML, disable_web_page_preview=True)

# ---------- My Settings ----------
async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        kws = list_keywords(u.id)
        r = s.execute(text('SELECT countries,proposal_template,trial_start,trial_end,license_until,is_active,is_blocked FROM "user" WHERE id=:id'),{"id":u.id}).fetchone()
    await update.effective_chat.send_message(settings_text(kws,r["countries"],r["proposal_template"],r["trial_start"],r["trial_end"],r["license_until"],bool(r["is_active"]),bool(r["is_blocked"])), parse_mode=ParseMode.HTML)

# ---------- Keywords ----------
def _parse_keywords(raw:str)->List[str]:
    parts=[p.strip() for chunk in raw.split(",") for p in chunk.split() if p.strip()]
    seen,out=set(),[]
    for p in parts:
        if p.lower() not in seen: seen.add(p.lower()); out.append(p)
    return out

async def addkeyword_cmd(update,context):
    if not context.args:
        await update.message.reply_text("Add keywords separated by commas. Example:\n<code>/addkeyword logo, lighting</code>",parse_mode=ParseMode.HTML);return
    kws=_parse_keywords(" ".join(context.args))
    with get_session() as s: u=get_or_create_user_by_tid(s,update.effective_user.id)
    add_keywords(u.id,kws)
    await update.message.reply_text("✅ Keywords updated.")

async def delkeyword_cmd(update,context):
    if not context.args:
        await update.message.reply_text("Usage: /delkeyword logo, sales");return
    kws=_parse_keywords(" ".join(context.args))
    with get_session() as s: u=get_or_create_user_by_tid(s,update.effective_user.id)
    delete_keywords(u.id,kws)
    await update.message.reply_text("🗑 Keywords removed.")

async def clearkeywords_cmd(update,context):
    with get_session() as s: u=get_or_create_user_by_tid(s,update.effective_user.id)
    clear_keywords(u.id)
    await update.message.reply_text("✅ All keywords cleared.")

# ---------- Self-test ----------
async def selftest_cmd(update,context):
    try:
        txt="<b>Logo Project Test</b>\n<b>Budget:</b> $50\n<b>Platform:</b> Freelancer\n<b>Match:</b> logo\n"
        kb=InlineKeyboardMarkup([[InlineKeyboardButton("📄 Proposal",url="https://freelancer.com"),InlineKeyboardButton("🔗 Original",url="https://freelancer.com")]])
        await update.effective_chat.send_message(txt,parse_mode=ParseMode.HTML,reply_markup=kb)
        ensure_feed_events_schema();record_event("freelancer");record_event("peopleperhour")
        await update.effective_chat.send_message("✅ Self-test OK — dummy events recorded.")
    except Exception as e:
        log.exception(e);await update.effective_chat.send_message("⚠️ Self-test failed.")
# ---------- Saved ----------
async def saved_cmd(update,context):
    try:
        uid=update.effective_user.id
        with get_session() as s:
            rows=s.execute(text("""
                SELECT je.platform,je.title,je.affiliate_url,je.budget_amount,je.budget_currency,je.created_at
                FROM saved_job sj LEFT JOIN job_event je ON sj.job_id=je.id
                WHERE sj.user_id=(SELECT id FROM "user" WHERE telegram_id=:t) ORDER BY sj.saved_at DESC LIMIT 10
            """),{"t":uid}).fetchall()
        if not rows: await update.effective_chat.send_message("💾 You have no saved jobs yet.");return
        msg="<b>💾 Saved Jobs:</b>\n"+"\n\n".join([f"• {r['title']}\n💰 {r['budget_amount']} {r['budget_currency']}\n🌍 {r['platform']}\n🔗 <a href='{r['affiliate_url']}'>Open</a>" for r in rows])
        await update.effective_chat.send_message(msg,parse_mode=ParseMode.HTML,disable_web_page_preview=True)
    except Exception as e:
        log.exception(e);await update.effective_chat.send_message("⚠️ Could not load saved jobs.")

# ---------- Contact Chat ----------
user_contact_state={}
async def contact_cmd(update,context):
    uid=update.effective_user.id;user_contact_state[uid]=True
    await update.effective_chat.send_message("✉️ Send your message to the admin.\nType /cancel to exit.")

async def message_router(update,context):
    uid=update.effective_user.id;txt=update.message.text
    if is_admin_user(uid) and txt.startswith("/reply"):
        parts=txt.split(maxsplit=2)
        if len(parts)<3:await update.message.reply_text("Usage: /reply <user_id> <msg>");return
        to=int(parts[1]);msg=parts[2]
        await context.bot.send_message(to,f"💬 Admin: {msg}");await update.message.reply_text("✅ Reply sent.");return
    if is_admin_user(uid):await update.message.reply_text("ℹ️ Use /reply <user_id> <msg> to respond.");return
    if user_contact_state.get(uid):
        for admin in all_admin_ids():
            kb=InlineKeyboardMarkup([[InlineKeyboardButton("💬 Reply",callback_data=f"reply:{uid}"),InlineKeyboardButton("❌ Decline",callback_data=f"decline:{uid}")],
                [InlineKeyboardButton("+30d",callback_data=f"grant:{uid}:30"),InlineKeyboardButton("+90d",callback_data=f"grant:{uid}:90"),InlineKeyboardButton("+180d",callback_data=f"grant:{uid}:180"),InlineKeyboardButton("+365d",callback_data=f"grant:{uid}:365")]])
            await context.bot.send_message(admin,f"📩 <b>New message from user</b>\nID: <a href='tg://user?id={uid}'>{uid}</a>\n\n{txt}",parse_mode=ParseMode.HTML,reply_markup=kb)
        await update.message.reply_text("✅ Message sent to admin.");user_contact_state[uid]=False;return

# ---------- Admin ----------
async def users_cmd(update,context):
    if not is_admin_user(update.effective_user.id):await update.effective_chat.send_message("⛔ Not allowed.");return
    with get_session() as s:
        rows=s.execute(text('SELECT telegram_id,username,is_active,is_blocked FROM "user" ORDER BY id DESC LIMIT 30')).fetchall()
    if not rows:await update.effective_chat.send_message("No users.");return
    lines=[f"{r['telegram_id']} | @{r['username'] or '-'} | Active:{r['is_active']} | Blocked:{r['is_blocked']}" for r in rows]
    await update.effective_chat.send_message("\n".join(lines))

# ---------- Menu ----------
async def menu_action_cb(update,context):
    q=update.callback_query;data=q.data;await q.answer()
    if data=="act:addkw":await q.message.chat.send_message("Use /addkeyword <text> to add new keywords.")
    elif data=="act:settings":await mysettings_cmd(update,context)
    elif data=="act:help":await q.message.chat.send_message(HELP_EN+help_footer(STATS_WINDOW_HOURS),parse_mode=ParseMode.HTML,disable_web_page_preview=True)
    elif data=="act:saved":await saved_cmd(update,context)
    elif data=="act:contact":await contact_cmd(update,context)
    elif data=="act:admin":
        if is_admin_user(update.effective_user.id):await users_cmd(update,context)
        else:await q.message.chat.send_message("⛔ Not authorized.")
    else:await q.message.chat.send_message("❌ Unknown action.")

# ---------- Build ----------
def build_application()->Application:
    app=ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",start_cmd))
    app.add_handler(CommandHandler("help",lambda u,c:u.message.reply_text(HELP_EN+help_footer(STATS_WINDOW_HOURS),parse_mode=ParseMode.HTML,disable_web_page_preview=True)))
    app.add_handler(CommandHandler("mysettings",mysettings_cmd))
    app.add_handler(CommandHandler("addkeyword",addkeyword_cmd))
    app.add_handler(CommandHandler("delkeyword",delkeyword_cmd))
    app.add_handler(CommandHandler("clearkeywords",clearkeywords_cmd))
    app.add_handler(CommandHandler("selftest",selftest_cmd))
    app.add_handler(CommandHandler("users",users_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,message_router))
    app.add_handler(CallbackQueryHandler(menu_action_cb,pattern=r"^act:"))
    return app
