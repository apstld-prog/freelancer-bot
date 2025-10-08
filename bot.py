# bot.py
# -*- coding: utf-8 -*-
import os, logging, html
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Tuple
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, Application,
    CommandHandler, CallbackQueryHandler,
    ContextTypes
)
from telegram.constants import ParseMode

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

def now_utc(): return datetime.now(UTC)
def is_admin_id(tg_id:int)->bool:
    adm=(os.getenv("ADMIN_ID") or "").strip()
    return str(tg_id)==str(adm) if adm else False
def _uid_field():
    for c in ("telegram_id","tg_id","chat_id","user_id","id"):
        if hasattr(User,c): return c
    raise RuntimeError("User id column not found")

def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Keywords",callback_data="act:add"),
         InlineKeyboardButton("⚙️ Settings",callback_data="act:settings")],
        [InlineKeyboardButton("🆘 Help",callback_data="act:help"),
         InlineKeyboardButton("💾 Saved",callback_data="act:saved")],
        [InlineKeyboardButton("📞 Contact",callback_data="act:contact"),
         InlineKeyboardButton("Admin",callback_data="act:admin")],
    ])

WELCOME_HEAD=(
    "👋 <b>Welcome to Freelancer Alert Bot!</b>\n\n"
    "🎁 <b>You have a 10-day free trial.</b>\n"
    "Automatically finds matching freelance jobs from top platforms and sends you instant alerts.\n\n"
    "Use <code>/help</code> to see how it works."
)
FEATURES_TEXT=(
    "✨ <b>Features</b>\n"
    "• Realtime job alerts (Freelancer API)\n"
    "• Proposal & Original links (safe wrappers)\n"
    "• Budget shown + USD conversion\n"
    "• ⭐ Keep / 🗑️ Delete buttons\n"
    "• 10-day free trial, extend via admin\n"
    "• Multi-keyword search (single/all modes)\n"
    "• Platforms by country (incl. GR boards)"
)
HELP_TEXT=(
    "🧭 <b>Help / How it works</b>\n\n"
    "1️⃣ Add keywords with <code>/addkeyword python, telegram</code> (comma-separated, English or Greek).\n"
    "2️⃣ Set your countries with <code>/setcountry US,UK</code> (or <code>ALL</code>).\n"
    "3️⃣ Save a proposal template with <code>/setproposal &lt;text&gt;</code> — Placeholders: "
    "<code>{jobtitle}</code>, <code>{experience}</code>, <code>{stack}</code>, <code>{availability}</code>, "
    "<code>{step1}</code>, <code>{step2}</code>, <code>{step3}</code>, <code>{budgettime}</code>, "
    "<code>{portfolio}</code>, <code>{name}</code>.\n"
    "4️⃣ When a job arrives you can:\n"
    "   ⭐ Keep it\n"
    "   🗑️ Delete it\n"
    "   📨 Proposal → direct link to job\n"
    "   🔗 Original → same wrapped job link\n\n"
    "➤ Use <code>/mysettings</code> anytime.\n"
    "➤ <code>/selftest</code> for a test job.\n"
    "➤ <code>/platforms CC</code> (e.g., <code>/platforms GR</code>)."
)

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
    return ("🛠️ <b>Your Settings</b>\n"
            f"• Keywords: {kw}\n• Countries: ALL\n• Proposal template: (none)\n\n"
            f"Trial start: {fmt(ts)}\nTrial ends: {fmt(te)}\nLicense until: {fmt(lu)}\n"
            f"<b>Expires:</b> {fmt(exp)} ({left(exp)})\n"
            f"Active: {active}   Blocked: {blocked}\n\n"
            "Platforms monitored:\n"
            "Freelancer.com, PeoplePerHour, Malt, Workana, Guru, 99designs, Toptal*, Codeable*, YunoJuno*, Worksome*, "
            "twago, freelancermap\n(* referral/curated)\n\n"
            "Greece: JobFind.gr, Skywalker.gr, Kariera.gr\n\n"
            "When your trial ends, please contact the admin to extend your access.")

# ===== helpers =====
async def _reply(update:Update, text:str):
    msg = update.effective_message or update.message
    return await msg.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

def _saved_list(db, uid_internal:int)->str:
    acts = db.query(JobAction).filter(JobAction.user_id==uid_internal, JobAction.action=="save")\
            .order_by(JobAction.created_at.desc()).limit(10).all()
    if not acts: return "No saved jobs yet."
    lines = ["💾 <b>Saved jobs</b> (latest 10)"]
    for a in acts:
        j = db.query(Job).filter(Job.id==a.job_id).one_or_none()
        if not j: continue
        t = html.escape(j.title or "Untitled")
        lines.append(f"• {t}\n  🔗 {j.original_url or j.url}")
    return "\n".join(lines)

# ===== Commands =====
async def start_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    await _reply(update, WELCOME_HEAD)
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
        await _reply(update, FEATURES_TEXT)
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
        await _reply(update, _saved_list(db, u.id))
    finally:
        try: db.close()
        except Exception: pass

async def feedstatus_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if not (SessionLocal and JobSent and Job):
        await _reply(update, "DB not available."); return
    since = now_utc() - timedelta(days=1)
    db=SessionLocal()
    try:
        q = db.execute(
            "SELECT j.source, COUNT(*) "
            "FROM job_sent s JOIN job j ON j.id=s.job_id "
            "WHERE s.created_at >= :since "
            "GROUP BY j.source ORDER BY j.source",
            {"since": since}
        )
        rows = list(q)
        title = "📊 <b>Sent jobs by platform (last 24h)</b>"
        if not rows:
            await _reply(update, f"{title}\n(0 results)"); return
        lines=[title]
        for src,cnt in rows:
            lines.append(f"• {src}: {int(cnt)}")
        await _reply(update, "\n".join(lines))
    finally:
        try: db.close()
        except Exception: pass

# ===== Inline job buttons =====
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

        if action=="delete":
            try:
                await q.message.edit_reply_markup(reply_markup=None)
                await q.message.edit_text(q.message.text_markdown + "\n\n~~deleted~~", parse_mode=None, disable_web_page_preview=True)
            except Exception:
                pass
            await q.answer("Deleted")
        else:
            await q.answer("Saved")
    finally:
        try: db.close()
        except Exception: pass

# ===== Menu buttons =====
async def menu_action_cb(update:Update, context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    if not q: return
    act=(q.data or "").split(":",1)[-1]

    if act=="add":
        await q.message.reply_text(
            "Type keywords using:\n<code>/addkeyword python, telegram</code>\n\nTip: you can send English or Greek.",
            parse_mode=ParseMode.HTML, disable_web_page_preview=True
        ); await q.answer(); return

    if act=="settings":
        await mysettings_cmd(update, context); await q.answer(); return

    if act=="help":
        await q.message.reply_text(HELP_TEXT, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        await q.answer(); return

    if act=="saved":
        if not (SessionLocal and User):
            await q.answer("DB not available."); return
        db=SessionLocal()
        try:
            u=db.query(User).filter(getattr(User,_uid_field())==str(q.from_user.id)).one()
            await q.message.reply_text(_saved_list(db,u.id), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        finally:
            try: db.close()
            except Exception: pass
        await q.answer(); return

    if act=="contact":
        await q.message.reply_text("Send your message here and the admin will reply to you.")
        await q.answer(); return

    if act=="admin":
        if is_admin_id(q.from_user.id):
            await q.message.reply_text("Admin panel: use /users, /grant <id> <days>, /block <id>, /unblock <id>, /feedstatus.")
        else:
            await q.message.reply_text("Admin only.")
        await q.answer(); return

    await q.answer()

# ===== Admin bits (όπως ήταν) =====
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
        "<b>Logo Reformatting to SVG</b>\n"
        "🧾 Budget: 30.0–250.0 AUD (~$19.5–$162.5)\n"
        "📎 Source: Freelancer\n"
        "🔍 Match: <b><u>logo</u></b>\n"
        "📝 I need my existing logo reformatted into SVG... (sample)\n"
        "⏱️ 2m ago"
    )
    await update.message.reply_text(" ", reply_markup=kb)

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
