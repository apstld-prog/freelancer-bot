# bot.py
# -*- coding: utf-8 -*-
# ==========================================================
# ⚠️ UI_LOCKED: DO NOT MODIFY any text layout, menu, or job card
# ==========================================================
import os, logging
from datetime import datetime, timedelta, timezone
from typing import List
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, Application,
    CommandHandler, CallbackQueryHandler,
    ContextTypes
)
from telegram.constants import ParseMode

# 👉 Fix for textual SQL in /feedstatus
try:
    from sqlalchemy import text as sql_text  # type: ignore
except Exception:
    sql_text = None  # falls back to plain string if SQLA not present

# === Database models import ===
SessionLocal=User=Keyword=Job=JobSent=JobAction=None
try:
    from db import SessionLocal as _S, User as _U, Keyword as _K, Job as _J, JobSent as _JS, JobAction as _JA, init_db as _init_db
    SessionLocal, User, Keyword, Job, JobSent, JobAction = _S, _U, _K, _J, _JS, _JA
except Exception:
    pass

log=logging.getLogger("bot")
logging.basicConfig(level=os.getenv("LOG_LEVEL","INFO"))
UTC=timezone.utc
DEFAULT_TRIAL_DAYS=int(os.getenv("DEFAULT_TRIAL_DAYS","10"))
UI_LOCKED = True  # <-- Do not modify appearance unless explicitly requested

def now_utc(): return datetime.now(UTC)
def is_admin_id(tg_id:int)->bool:
    adm=(os.getenv("ADMIN_ID") or "").strip()
    return str(tg_id)==str(adm) if adm else False
def _uid_field():
    for c in ("telegram_id","tg_id","chat_id","user_id","id"):
        if hasattr(User,c): return c
    raise RuntimeError("User id column not found")

# ==========================================================
# MAIN MENU (Classic style)
# ==========================================================
def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Keywords",callback_data="act:add"),
         InlineKeyboardButton("⚙️ Settings",callback_data="act:settings")],
        [InlineKeyboardButton("🆘 Help",callback_data="act:help"),
         InlineKeyboardButton("💾 Saved",callback_data="act:saved")],
        [InlineKeyboardButton("📞 Contact",callback_data="act:contact"),
         InlineKeyboardButton("Admin",callback_data="act:admin")],
    ])

# ==========================================================
# TEXTS (Classic UI)
# ==========================================================
WELCOME_CLASSIC=(
    "👋 Welcome to Freelancer Alert Bot!\n\n"
    "🎁 You have a 10-day free trial.\n"
    "Automatically finds matching freelance jobs from top platforms and sends you instant alerts.\n\n"
    "Use /help to see how it works."
)

HELP_TEXT=(
    "🧭 Help / How it works\n\n"
    "1) Add keywords with /addkeyword python, telegram (comma-separated, English or Greek).\n"
    "2) Set your countries with /setcountry US,UK (or ALL).\n"
    "3) Save a proposal template with /setproposal <text> (placeholders: {jobtitle}, {experience}, {stack}, {availability}, {step1}, {step2}, {step3}, {budgettime}, {portfolio}, {name}).\n"
    "4) When a job arrives you can: keep, delete, open Proposal or Original link.\n\n"
    "Use /mysettings anytime. Try /selftest for a sample. /platforms CC (e.g., /platforms GR)."
)

# ==========================================================
# FUNCTIONS
# ==========================================================
def _collect_keywords(u) -> List[str]:
    kws=[]
    try:
        rel=getattr(u,"keywords",None)
        if rel is not None:
            for k in list(rel):
                t=getattr(k,"keyword",None) or getattr(k,"text",None)
                if t: kws.append(str(t))
    except Exception:
        pass
    return kws

def settings_card(u, kws:List[str])->str:
    ts=getattr(u,"started_at",None) or getattr(u,"trial_start",None)
    te=getattr(u,"trial_until",None) or getattr(u,"trial_ends",None)
    lu=getattr(u,"access_until",None) or getattr(u,"license_until",None)
    exp = lu or te
    def fmt(dt):
        if not dt: return "None"
        try: return dt.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%SZ")
        except Exception: return str(dt)
    def left(x):
        if not x: return "—"
        s=(x - now_utc()).total_seconds()
        if s<0: return f"expired {int(abs(s)//86400)+1} day(s) ago"
        return f"in {int(s)//86400 + 1} day(s)"
    active="✅" if (not getattr(u,"is_blocked",False) and exp and exp>=now_utc()) else "❌"
    blocked="✅" if getattr(u,"is_blocked",False) else "❌"
    kw=", ".join(kws) if kws else "—"
    return (
        "🛠️ Your Settings\n"
        f"• Keywords: {kw}\n• Countries: ALL\n• Proposal template: (none)\n\n"
        f"Trial start: {fmt(ts)}\nTrial ends: {fmt(te)}\nLicense until: {fmt(lu)}\n"
        f"Expires: {fmt(exp)} ({left(exp)})\n"
        f"Active: {active}   Blocked: {blocked}\n\n"
        "Platforms monitored:\n"
        "Freelancer.com, PeoplePerHour, Malt, Workana, Guru, 99designs, Toptal*, Codeable*, YunoJuno*, Worksome*, "
        "twago, freelancermap (*referral/curated)\n\n"
        "Greece: JobFind.gr, Skywalker.gr, Kariera.gr\n\n"
        "When your trial ends, please contact the admin to extend your access."
    )

async def _reply(update:Update, text:str, kb:InlineKeyboardMarkup|None=None):
    msg = update.effective_message or update.message
    return await msg.reply_text(text, reply_markup=kb, disable_web_page_preview=True)

# ==========================================================
# COMMANDS
# ==========================================================
async def start_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    await _reply(update, WELCOME_CLASSIC, main_kb())
    if not (SessionLocal and User): return
    db=SessionLocal()
    try:
        u=db.query(User).filter(getattr(User,_uid_field())==str(update.effective_user.id)).one_or_none()
        if not u:
            u=User(telegram_id=str(update.effective_user.id),
                   started_at=now_utc(),
                   trial_until=now_utc()+timedelta(days=DEFAULT_TRIAL_DAYS),
                   is_blocked=False)
            db.add(u); db.commit(); db.refresh(u)
        kws=_collect_keywords(u)
        await _reply(update, settings_card(u,kws))
    finally:
        try: db.close()
        except Exception: pass

async def help_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    await _reply(update, HELP_TEXT)

async def mysettings_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if not (SessionLocal and User):
        await _reply(update, "DB not available."); return
    db=SessionLocal()
    try:
        u=db.query(User).filter(getattr(User,_uid_field())==str(update.effective_user.id)).one_or_none()
        if not u: 
            await _reply(update, "User not found."); return
        kws=_collect_keywords(u)
        await _reply(update, settings_card(u,kws))
    finally:
        try: db.close()
        except Exception: pass

async def saved_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if not all([SessionLocal, JobAction, Job, User]): 
        await _reply(update, "DB not available."); return
    db=SessionLocal()
    try:
        u=db.query(User).filter(getattr(User,_uid_field())==str(update.effective_user.id)).one()
        acts = db.query(JobAction).filter(JobAction.user_id==u.id, JobAction.action=="save")\
                .order_by(JobAction.created_at.desc()).limit(10).all()
        if not acts:
            await _reply(update, "No saved jobs yet."); return
        lines=["💾 Saved jobs (latest 10)"]
        for a in acts:
            j = db.query(Job).filter(Job.id==a.job_id).one_or_none()
            if j:
                lines.append(f"• {j.title or 'Untitled'}\n  {j.original_url or j.url}")
        await _reply(update, "\n".join(lines))
    finally:
        try: db.close()
        except Exception: pass

async def feedstatus_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if not (SessionLocal and JobSent and Job):
        await _reply(update, "DB not available."); return
    since = now_utc() - timedelta(days=1)
    db=SessionLocal()
    try:
        sql = (
            "SELECT j.source, COUNT(*) "
            "FROM job_sent s JOIN job j ON j.id=s.job_id "
            "WHERE s.created_at >= :since GROUP BY j.source ORDER BY j.source"
        )
        stmt = sql_text(sql) if sql_text else sql  # SQLAlchemy 2.x requires text()
        q = db.execute(stmt, {"since": since})
        rows = list(q)
        title = "📊 Sent jobs by platform (last 24h)"
        if not rows:
            await _reply(update, f"{title}\n(0 results)"); return
        lines=[title] + [f"• {src}: {int(cnt)}" for src,cnt in rows]
        await _reply(update, "\n".join(lines))
    finally:
        try: db.close()
        except Exception: pass

# ==========================================================
# INLINE BUTTON CALLBACKS
# ==========================================================
async def job_buttons_cb(update:Update, context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    if not q or not (SessionLocal and JobAction and User): 
        if q: await q.answer()
        return
    data=q.data or ""
    if not (data.startswith("job:save:") or data.startswith("job:delete:")):
        await q.answer(); return
    action, jid = ("save", data.split(":")[-1]) if "save" in data else ("delete", data.split(":")[-1])

    db=SessionLocal()
    try:
        u=db.query(User).filter(getattr(User,_uid_field())==str(q.from_user.id)).one_or_none()
        if not u:
            await q.answer("User not found."); return
        try:
            ja = JobAction(user_id=u.id, job_id=int(jid), action=action)
            db.add(ja); db.commit()
        except Exception:
            db.rollback()
        await q.answer("Saved" if action=="save" else "Deleted")
    finally:
        try: db.close()
        except Exception: pass

async def menu_action_cb(update:Update, context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    if not q: return
    act=(q.data or "").split(":",1)[-1]
    if act=="add":
        await q.message.reply_text("Type keywords using:\n/addkeyword python, telegram", disable_web_page_preview=True)
    elif act=="settings":
        await mysettings_cmd(update, context)
    elif act=="help":
        await q.message.reply_text(HELP_TEXT, disable_web_page_preview=True)
    elif act=="saved":
        await saved_cmd(update, context)
    elif act=="contact":
        await q.message.reply_text("Send your message here and the admin will reply to you.")
    elif act=="admin":
        if is_admin_id(q.from_user.id):
            await q.message.reply_text("Admin panel: use /users, /grant <id> <days>, /block <id>, /unblock <id>, /feedstatus.")
        else:
            await q.message.reply_text("Admin only.")
    await q.answer()

# ==========================================================
# ADMIN COMMANDS
# ==========================================================
async def users_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if not is_admin_id(update.effective_user.id):
        await _reply(update, "Admin only."); return
    if not (SessionLocal and User):
        await _reply(update, "DB not available."); return
    db=SessionLocal()
    try:
        rows=db.query(User).all()
        lines=["Users"]
        for u in rows:
            tid=getattr(u,_uid_field(),None)
            kws=_collect_keywords(u)
            trial=getattr(u,"trial_until",None)
            lic  =getattr(u,"access_until",None)
            act="✅" if (not getattr(u,"is_blocked",False) and (lic or trial) and (lic or trial)>=now_utc()) else "❌"
            blk="✅" if getattr(u,"is_blocked",False) else "❌"
            lines.append(f"• {tid} — kw:{len(kws)} | trial:{trial} | lic:{lic} | A:{act} B:{blk}")
        await _reply(update, "\n".join(lines))
    finally:
        try: db.close()
        except Exception: pass

async def platforms_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    cc=" ".join(context.args).strip().upper() if context.args else ""
    if not cc:
        await _reply(update, "Usage: /platforms CC  (e.g., /platforms GR or /platforms ALL)")
        return
    if cc=="GR":
        txt="Greece: JobFind.gr, Skywalker.gr, Kariera.gr"
    else:
        txt=("Global: Freelancer.com, PeoplePerHour, Malt, Workana, Guru, 99designs, "
             "Toptal*, Codeable*, YunoJuno*, Worksome*, twago, freelancermap (*referral/curated)")
    await _reply(update, txt)

async def selftest_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    kb=InlineKeyboardMarkup([
        [InlineKeyboardButton("📨 Proposal", url="https://www.freelancer.com"),
         InlineKeyboardButton("🔗 Original", url="https://www.freelancer.com")],
        [InlineKeyboardButton("⭐ Save", callback_data="job:save:999999"),
         InlineKeyboardButton("🗑️ Delete", callback_data="job:delete:999999")],
    ])
    await _reply(update,
        "Logo Reformatting to SVG\n"
        "🧾 Budget: 30.0–250.0 AUD (~$19.5–$162.5)\n"
        "📎 Source: Freelancer\n"
        "🔍 Match: logo\n"
        "📝 I need my existing logo reformatted into SVG... (sample)\n"
        "⏱️ 2m ago",
        kb
    )

# ==========================================================
# APPLICATION BUILDER
# ==========================================================
def build_application()->Application:
    if '_init_db' in globals() and callable(_init_db):
        try: _init_db()
        except Exception: pass

    token=(os.getenv("BOT_TOKEN") or "").strip()
    app=ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))
    app.add_handler(CommandHandler("saved", saved_cmd))
    app.add_handler(CommandHandler("feedstatus", feedstatus_cmd))
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CommandHandler("platforms", platforms_cmd))
    app.add_handler(CommandHandler("selftest", selftest_cmd))

    app.add_handler(CallbackQueryHandler(job_buttons_cb, pattern=r"^job:(save|delete):"))
    app.add_handler(CallbackQueryHandler(menu_action_cb, pattern=r"^act:"))
    return app
