# bot.py — full fixed version
import os, re, asyncio, logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Set
from types import SimpleNamespace
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
try:
    from telegram.ext import JobQueue
except Exception:
    JobQueue = None  # type: ignore
from sqlalchemy import text
from db import ensure_schema, get_session, get_or_create_user_by_tid
from config import ADMIN_IDS, TRIAL_DAYS, STATS_WINDOW_HOURS
from db_events import ensure_feed_events_schema, get_platform_stats, record_event
from db_keywords import (
    list_keywords, add_keywords, count_keywords,
    ensure_keyword_unique, delete_keywords, clear_keywords
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

BOT_TOKEN = (
    os.getenv("TELEGRAM_BOT_TOKEN")
    or os.getenv("BOT_TOKEN")
    or os.getenv("TELEGRAM_TOKEN")
)
if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN env var is required")

# ---------- helpers ----------
FX = {"EUR": 1.08, "GBP": 1.25, "USD": 1.0}
def usd_fmt(amount: Optional[float], cur: str) -> str:
    if amount is None: return "N/A"
    cur = (cur or "USD").upper()
    usd = amount * FX.get(cur, 1.0)
    if cur == "USD": return f"{amount:.2f} USD"
    return f"{amount:.2f} {cur} (~${usd:.2f} USD)"

def get_db_admin_ids() -> Set[int]:
    try:
        with get_session() as s:
            rows = s.execute(text('SELECT telegram_id FROM "user" WHERE is_admin=TRUE')).fetchall()
        return {int(r["telegram_id"]) for r in rows if r["telegram_id"]}
    except Exception: return set()
def all_admin_ids() -> Set[int]:
    seed = set(int(x) for x in (ADMIN_IDS or []))
    return seed | get_db_admin_ids()
def is_admin_user(tid: int) -> bool:
    return tid in all_admin_ids()

def main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    kb = [
        [
            InlineKeyboardButton("➕ Add Keywords", callback_data="act:addkw"),
            InlineKeyboardButton("⚙️ Settings", callback_data="act:settings"),
        ],
        [
            InlineKeyboardButton("🆘 Help", callback_data="act:help"),
            InlineKeyboardButton("💾 Saved", callback_data="act:saved"),
        ],
        [InlineKeyboardButton("📨 Contact", callback_data="act:contact")],
    ]
    if is_admin:
        kb.append([InlineKeyboardButton("🔥 Admin", callback_data="act:admin")])
    return InlineKeyboardMarkup(kb)

def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("👥 Users", callback_data="adm:users"),
                InlineKeyboardButton("📣 Broadcast", callback_data="adm:broadcast_prompt"),
            ],
            [
                InlineKeyboardButton("📈 Feed Status", callback_data="adm:feedstatus"),
                InlineKeyboardButton("🎁 Grant License", callback_data="adm:grantmenu"),
            ],
            [
                InlineKeyboardButton("🚫 Block", callback_data="adm:block_prompt"),
                InlineKeyboardButton("✅ Unblock", callback_data="adm:unblock_prompt"),
            ],
        ]
    )

HELP_EN = (
    "🧭 <b>Help / How it works</b>\n\n"
    "1️⃣ Add keywords with <code>/addkeyword python, telegram</code>\n"
    "2️⃣ Set your countries via <code>/setcountry US,UK</code>\n"
    "3️⃣ Save a proposal template with <code>/setproposal &lt;text&gt;</code>\n"
    "4️⃣ When a job arrives you can ⭐ Save • 🗑 Delete • 📄 Proposal • 🔗 Original\n\n"
    "• Use <code>/mysettings</code> anytime to review setup.\n"
    "• Try <code>/selftest</code> for 2 sample jobs."
)

def welcome_text(expiry: Optional[datetime]) -> str:
    extra = f"\n<b>Free trial ends:</b> {expiry.strftime('%Y-%m-%d %H:%M UTC')}" if expiry else ""
    return (
        "👋 <b>Welcome to Freelancer Alert Bot!</b>\n\n"
        "🎁 You have a <b>10-day free trial</b>.\n"
        "The bot finds freelance jobs from top platforms and sends alerts instantly."
        f"{extra}\n\nUse <code>/help</code> to see how it works."
    )

def settings_text(kws, countries, proposal, trial_start, trial_end, license_until, active, blocked):
    def tick(v): return "✅" if v else "❌"
    k = ", ".join(kws) if kws else "(none)"
    c = countries or "ALL"
    te = trial_end.isoformat().replace("+00:00","Z") if trial_end else "—"
    lic = license_until.isoformat().replace("+00:00","Z") if license_until else "None"
    return (
        "🛠 <b>Your Settings</b>\n"
        f"• Keywords: {k}\n• Countries: {c}\n• Proposal: {(proposal and '(saved)') or '(none)'}\n\n"
        f"Trial ends: {te} UTC\nLicense until: {lic}\n"
        f"✅ Active: {tick(active)}  ⛔ Blocked: {tick(blocked)}"
    )

# ---------- commands ----------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        s.execute('UPDATE "user" SET trial_start=COALESCE(trial_start,NOW() AT TIME ZONE \'UTC\') WHERE id=%(i)s', {"i":u.id})
        s.execute('UPDATE "user" SET trial_end=COALESCE(trial_end,(NOW() AT TIME ZONE \'UTC\')+make_interval(days=>%(d)s)) WHERE id=%(i)s',{"i":u.id,"d":TRIAL_DAYS})
        row = s.execute('SELECT COALESCE(license_until,trial_end) AS expiry FROM "user" WHERE id=%(i)s',{"i":u.id}).fetchone()
        expiry = row["expiry"] if row else None
        s.commit()
    await update.effective_chat.send_message(welcome_text(expiry),parse_mode=ParseMode.HTML,reply_markup=main_menu_kb(is_admin=is_admin_user(update.effective_user.id)))
    await update.effective_chat.send_message(HELP_EN,parse_mode=ParseMode.HTML,disable_web_page_preview=True)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(HELP_EN,parse_mode=ParseMode.HTML)

async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u=get_or_create_user_by_tid(s,update.effective_user.id)
        kws=list_keywords(u.id)
        row=s.execute(text('SELECT countries,proposal_template,trial_end,license_until,is_active,is_blocked FROM "user" WHERE id=:i'),{"i":u.id}).fetchone()
    await update.effective_chat.send_message(settings_text(kws,row["countries"],row["proposal_template"],None,row["trial_end"],row["license_until"],bool(row["is_active"]),bool(row["is_blocked"])),parse_mode=ParseMode.HTML)

def _parse_keywords(raw:str)->List[str]:
    parts=[p.strip() for chunk in raw.split(",") for p in chunk.split() if p.strip()]
    seen,out=set(),[]
    for p in parts:
        lp=p.lower()
        if lp not in seen:
            seen.add(lp);out.append(p)
    return out

async def addkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Add keywords separated by commas.\nExample: /addkeyword logo, lighting");return
    kws=_parse_keywords(" ".join(context.args))
    if not kws: await update.message.reply_text("No valid keywords.");return
    with get_session() as s:
        u=get_or_create_user_by_tid(s,update.effective_user.id)
    n=add_keywords(u.id,kws)
    cur=list_keywords(u.id)
    await update.message.reply_text(("✅ Added %d new keywords."%n if n else "ℹ️ Already exist.")+"\nCurrent: "+", ".join(cur))

async def delkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: await update.message.reply_text("Usage: /delkeyword logo, sales");return
    kws=_parse_keywords(" ".join(context.args))
    with get_session() as s: u=get_or_create_user_by_tid(s,update.effective_user.id)
    removed=delete_keywords(u.id,kws)
    left=list_keywords(u.id)
    await update.message.reply_text(f"🗑 Removed {removed}.\nCurrent: "+", ".join(left))

async def clearkeywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Yes",callback_data="kw:clear:yes"),InlineKeyboardButton("❌ No",callback_data="kw:clear:no")]])
    await update.message.reply_text("Clear ALL your keywords?",reply_markup=kb)
async def kw_clear_confirm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    if (q.data or "")!="kw:clear:yes":await q.edit_message_text("Cancelled.");return
    with get_session() as s:u=get_or_create_user_by_tid(s,q.from_user.id)
    n=clear_keywords(u.id);await q.edit_message_text(f"🗑 Cleared {n} keyword(s).")

# -------- Contact chat identical UI --------
def _pairstore(app):return app.bot_data.setdefault("pairs",{"u2a":{},"a2u":{}})
def pair_admin_user(app,admin_id,user_id):p=_pairstore(app);p["u2a"][user_id]=admin_id;p["a2u"][admin_id]=user_id
def get_paired_admin(app,user_id):return _pairstore(app)["u2a"].get(user_id)
def get_paired_user(app,admin_id):return _pairstore(app)["a2u"].get(admin_id)
def unpair(app,admin_id=None,user_id=None):
    p=_pairstore(app)
    if admin_id is not None:
        uid=p["a2u"].pop(admin_id,None)
        if uid is not None:p["u2a"].pop(uid,None)
    if user_id is not None:
        aid=p["u2a"].pop(user_id,None)
        if aid is not None:p["a2u"].pop(aid,None)

async def contact_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message("✉️ Send a message to admin below. /cancel to stop.",parse_mode=ParseMode.HTML)
    txt=f"📩 <b>New message from user</b>\nID: <code>{update.effective_user.id}</code>\n(Waiting for reply…)"
    kb=InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Reply",callback_data=f"adm:reply:{update.effective_user.id}"),
         InlineKeyboardButton("❌ Decline",callback_data=f"adm:decline:{update.effective_user.id}")],
        [InlineKeyboardButton("+30d",callback_data=f"adm:grant:{update.effective_user.id}:30"),
         InlineKeyboardButton("+90d",callback_data=f"adm:grant:{update.effective_user.id}:90")],
        [InlineKeyboardButton("+180d",callback_data=f"adm:grant:{update.effective_user.id}:180"),
         InlineKeyboardButton("+365d",callback_data=f"adm:grant:{update.effective_user.id}:365")],
    ])
    for aid in all_admin_ids():
        try:await context.bot.send_message(aid,txt,parse_mode=ParseMode.HTML,reply_markup=kb)
        except Exception:pass

async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    unpair(context.application,user_id=update.effective_user.id);await update.message.reply_text("Chat cancelled.")

async def incoming_message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text or update.message.text.startswith("/"):return
    sender=update.effective_user.id;app=context.application
    if is_admin_user(sender):
        target=get_paired_user(app,sender)
        if target:
            try:await context.bot.send_message(target,update.message.text)
            except Exception:pass
            return
    target_admin=get_paired_admin(app,sender)
    if target_admin:
        try:
            await context.bot.send_message(target_admin,f"✉️ From {sender}:\n\n{update.message.text}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💬 Reply",callback_data=f"adm:reply:{sender}"),
                     InlineKeyboardButton("❌ Decline",callback_data=f"adm:decline:{sender}")],
                    [InlineKeyboardButton("+30d",callback_data=f"adm:grant:{sender}:30"),
                     InlineKeyboardButton("+90d",callback_data=f"adm:grant:{sender}:90")],
                    [InlineKeyboardButton("+180d",callback_data=f"adm:grant:{sender}:180"),
                     InlineKeyboardButton("+365d",callback_data=f"adm:grant:{sender}:365")],
                ]))
        except Exception:pass
        return
    for aid in all_admin_ids():
        try:
            await context.bot.send_message(aid,f"✉️ <b>New message</b> from <code>{sender}</code>\n\n{update.message.text}",
                parse_mode=ParseMode.HTML,reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💬 Reply",callback_data=f"adm:reply:{sender}"),
                     InlineKeyboardButton("❌ Decline",callback_data=f"adm:decline:{sender}")],
                    [InlineKeyboardButton("+30d",callback_data=f"adm:grant:{sender}:30"),
                     InlineKeyboardButton("+90d",callback_data=f"adm:grant:{sender}:90")],
                    [InlineKeyboardButton("+180d",callback_data=f"adm:grant:{sender}:180"),
                     InlineKeyboardButton("+365d",callback_data=f"adm:grant:{sender}:365")],
                ]))
        except Exception:pass
    await update.message.reply_text("Thanks! Message forwarded 👌")
# ----------- Saved + Selftest -----------
async def saved_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        with get_session() as s:
            u=get_or_create_user_by_tid(s,update.effective_user.id)
            s.execute(text("""CREATE TABLE IF NOT EXISTS saved_job(
                id SERIAL PRIMARY KEY,user_id BIGINT,job_id BIGINT,
                saved_at TIMESTAMP DEFAULT (NOW() AT TIME ZONE 'UTC'))"""))
            rows=s.execute(text("""
                SELECT sj.job_id,je.title,je.description,je.original_url,
                       je.budget_amount,je.budget_currency,je.platform
                  FROM saved_job sj
             LEFT JOIN job_event je ON je.id=sj.job_id
                 WHERE sj.user_id=:u ORDER BY sj.id DESC LIMIT 20"""),{"u":u.id}).fetchall()
        if not rows:
            await update.effective_chat.send_message("💾 No saved jobs yet.");return
        for r in rows:
            b=usd_fmt(r["budget_amount"],r["budget_currency"] or "USD")
            msg=f"<b>{r['title']}</b>\n💰 <b>Budget:</b> {b}\n🌐 {r['platform']}"
            kb=InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Original",url=r["original_url"] or "")],
                                      [InlineKeyboardButton("🗑 Delete",callback_data=f"saved:del:{r['job_id']}")]])
            await update.effective_chat.send_message(msg,parse_mode=ParseMode.HTML,reply_markup=kb)
            await asyncio.sleep(0.25)
    except Exception as e:
        log.exception("saved list: %s",e);await update.effective_chat.send_message("⚠️ Saved unavailable.")

async def job_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer();msg=q.message
    data=q.data
    if data=="job:save":
        try:
            with get_session() as s:
                u=get_or_create_user_by_tid(s,update.effective_user.id)
                s.execute(text("""CREATE TABLE IF NOT EXISTS saved_job(
                    id SERIAL PRIMARY KEY,user_id BIGINT,job_id BIGINT,
                    saved_at TIMESTAMP DEFAULT (NOW() AT TIME ZONE 'UTC'))"""))
                je=s.execute(text("""
                    INSERT INTO job_event(platform,title,description,original_url,created_at)
                    VALUES('manual',:t,:d,:o,NOW() AT TIME ZONE 'UTC') RETURNING id
                """),{"t":msg.text_html or msg.text,"d":msg.text_html or msg.text,"o":""}).fetchone()
                s.execute(text("INSERT INTO saved_job(user_id,job_id) VALUES(:u,:j)"),{"u":u.id,"j":je["id"]})
                s.commit()
            await msg.delete()
        except Exception as e: log.exception("save err %s",e)
    elif data=="job:delete":
        try: await msg.delete()
        except: pass

async def saved_delete_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    if not q.data.startswith("saved:del:"):return
    job_id=int(q.data.split(":")[2])
    with get_session() as s:
        u=get_or_create_user_by_tid(s,q.from_user.id)
        s.execute(text("DELETE FROM saved_job WHERE user_id=:u AND job_id=:j"),{"u":u.id,"j":job_id})
        s.commit()
    try: await q.message.delete()
    except: pass

async def selftest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        msg1=("<b>Email Signature from Existing Logo</b>\n"
              f"💰 <b>Budget:</b> 20.00 EUR (~${20.00*FX['EUR']:.2f} USD)\n"
              "🌐 <b>Source:</b> Freelancer\n"
              "🔍 <b>Match:</b> logo\n📝 Create editable version of email signature\n"
              f"🕓 <b>Posted:</b> {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}")
        kb1=InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 Proposal",url="https://freelancer.com/job/demo1"),
             InlineKeyboardButton("🔗 Original",url="https://freelancer.com/job/demo1")],
            [InlineKeyboardButton("⭐ Save",callback_data="job:save"),
             InlineKeyboardButton("🗑 Delete",callback_data="job:delete")]
        ])
        await update.effective_chat.send_message(msg1,parse_mode=ParseMode.HTML,reply_markup=kb1)
        record_event("freelancer")

        await asyncio.sleep(0.5)
        msg2=("<b>Landing Page Development</b>\n"
              "💰 <b>Budget:</b> 120.00 USD\n"
              "🌐 <b>Source:</b> PeoplePerHour\n"
              "🔍 <b>Match:</b> wordpress\n📝 Create WP landing page\n"
              f"🕓 <b>Posted:</b> {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}")
        kb2=InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 Proposal",url="https://peopleperhour.com/job/demo2"),
             InlineKeyboardButton("🔗 Original",url="https://peopleperhour.com/job/demo2")],
            [InlineKeyboardButton("⭐ Save",callback_data="job:save"),
             InlineKeyboardButton("🗑 Delete",callback_data="job:delete")]
        ])
        await update.effective_chat.send_message(msg2,parse_mode=ParseMode.HTML,reply_markup=kb2)
        record_event("peopleperhour")

        await update.effective_chat.send_message("✅ Self-test completed — 2 sample jobs posted.")
    except Exception as e:
        log.exception("selftest: %s",e)
        await update.effective_chat.send_message("⚠️ Self-test failed.")

# ---------- Build ----------
def build_application() -> Application:
    ensure_schema();ensure_feed_events_schema();ensure_keyword_unique()
    app=ApplicationBuilder().token(BOT_TOKEN).build()
    for cmd,func in [
        ("start",start_cmd),("help",help_cmd),("mysettings",mysettings_cmd),
        ("addkeyword",addkeyword_cmd),("delkeyword",delkeyword_cmd),
        ("clearkeywords",clearkeywords_cmd),("selftest",selftest_cmd),
        ("contact",contact_cmd),("cancel",cancel_cmd),
    ]: app.add_handler(CommandHandler(cmd,func))
    app.add_handler(CallbackQueryHandler(job_action_cb,pattern=r"^job:(save|delete)$"))
    app.add_handler(CallbackQueryHandler(saved_delete_cb,pattern=r"^saved:del:\d+$"))
    app.add_handler(CallbackQueryHandler(kw_clear_confirm_cb,pattern=r"^kw:clear:(yes|no)$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,incoming_message_router))
    return app
