# bot.py
# -*- coding: utf-8 -*-
import os, logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, Application,
    CommandHandler, CallbackQueryHandler,
    ContextTypes
)
from telegram.constants import ParseMode

# ===== DB wiring =====
SessionLocal=None; User=None; Keyword=None; Job=None; JobSent=None
try:
    from db import SessionLocal as _S, User as _U, Keyword as _K, Job as _J, JobSent as _JS, init_db as _init_db
    SessionLocal, User, Keyword, Job, JobSent = _S, _U, _K, _J, _JS
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

# ===== UI text =====
def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Keywords",callback_data="act:add"),
         InlineKeyboardButton("⚙️ Settings",callback_data="act:settings")],
        [InlineKeyboardButton("🆘 Help",callback_data="act:help"),
         InlineKeyboardButton("💾 Saved",callback_data="act:saved")],
        [InlineKeyboardButton("📞 Contact",callback_data="act:contact"),
         InlineKeyboardButton("👑 Admin",callback_data="act:admin")],
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

# ===== helpers =====
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
        return f"in {int(s//86400)+1} day(s)"
    active="✅" if (not getattr(u,"is_blocked",False) and exp and exp>=now_utc()) else "❌"
    blocked="✅" if getattr(u,"is_blocked",False) else "❌"
    kw=", ".join(kws) if kws else "—"
    return ("🛠️ <b>Your Settings</b>\n"
            f"• Keywords: {kw}\n• Countries: ALL\n• Proposal template: (none)\n\n"
            f"🟢 Trial start: {fmt(ts)}\n⏳ Trial ends: {fmt(te)}\n🔑 License until: {fmt(lu)}\n"
            f"📅 <b>Expires:</b> {fmt(exp)} ({left(exp)})\n"
            f"🟢 Active: {active}\n⛔ Blocked: {blocked}\n\n"
            "📜 Platforms monitored:\n"
            "Freelancer.com, PeoplePerHour, Malt, Workana, Guru, 99designs, Toptal*, Codeable*, YunoJuno*, Worksome*, "
            "twago, freelancermap\n(* referral/curated platforms)\n\n"
            "Greece: JobFind.gr, Skywalker.gr, Kariera.gr\n\n"
            "When your trial ends, please <b>contact the admin</b> to extend your access.")

# ===== commands =====
async def start_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME_HEAD, reply_markup=main_kb(),
                                    parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    if not SessionLocal or not User: return
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
        await update.message.reply_text(settings_card(u,kws), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        await update.message.reply_text(FEATURES_TEXT, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    finally:
        try: db.close()
        except Exception: pass

async def help_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

async def selftest_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    kb=InlineKeyboardMarkup([
        [InlineKeyboardButton("📨 Proposal", url="https://www.freelancer.com"),
         InlineKeyboardButton("🔗 Original", url="https://www.freelancer.com")],
        [InlineKeyboardButton("⭐ Save", callback_data="job:save:selftest"),
         InlineKeyboardButton("🗑️ Delete", callback_data="job:delete:selftest")],
    ])
    await update.message.reply_text(
        "<b>Logo Reformatting to SVG</b>\n"
        "🧾 Budget: 30.0–250.0 AUD (~$19.5–$162.5)\n"
        "📎 Source: Freelancer\n"
        "🔍 Match: <b><u>logo</u></b>\n"
        "📝 I need my existing logo reformatted into SVG... (sample)\n"
        "⏱️ 2m ago",
        parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=kb
    )

# ===== inline buttons (jobs) =====
async def job_buttons_cb(update:Update, context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    if not q: return
    data=q.data or ""
    if data.startswith("job:save:"):
        await q.answer("Saved ⭐", show_alert=False)
    elif data.startswith("job:delete:"):
        await q.answer("Deleted 🗑️", show_alert=False)
    else:
        await q.answer()

# ===== inline buttons (menu) =====
async def menu_action_cb(update:Update, context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    if not q: return
    act=(q.data or "").split(":",1)[-1]

    if act=="add":
        msg=("Type keywords using:\n"
             "<code>/addkeyword python, telegram</code>\n\n"
             "Tip: you can send English or Greek.")
        await q.message.reply_text(msg, parse_mode=ParseMode.HTML)
        await q.answer()
        return

    if act=="settings":
        if not (SessionLocal and User):
            await q.answer(); return
        db=SessionLocal()
        try:
            u=db.query(User).filter(getattr(User,_uid_field())==str(q.from_user.id)).one_or_none()
            if u:
                kws=_collect_keywords(u)
                await q.message.reply_text(settings_card(u,kws), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        finally:
            try: db.close()
            except Exception: pass
        await q.answer()
        return

    if act=="help":
        await q.message.reply_text(HELP_TEXT, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        await q.answer(); return

    if act=="saved":
        await q.message.reply_text("Saved jobs list will appear here soon. (WIP)")
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

# ===== /feedstatus (JOIN job_sent -> job) =====
async def feedstatus_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if not is_admin_id(update.effective_user.id):
        await update.message.reply_text("Admin only."); return
    if not all([SessionLocal, Job, JobSent]):
        await update.message.reply_text("DB not available."); return
    db=SessionLocal()
    try:
        since=now_utc()-timedelta(hours=24)
        rows=(db.query(Job.source)
                .join(JobSent, JobSent.job_id==Job.id)
                .filter(JobSent.created_at>=since)
                .all())
        counts:Dict[str,int]={}
        for (src,) in rows:
            counts[src]=counts.get(src,0)+1
        ordered=["99designs","Careerjet","Codeable","Freelancer","Guru","JobFind","Kariera","Malt",
                 "PeoplePerHour","Skywalker","Toptal","Workana","Worksome","Wripple","YunoJuno",
                 "freelancermap","twago"]
        lines=["📊 <b>Sent jobs by platform (last 24h)</b>"]
        for name in ordered:
            lines.append(f"• {name}: {counts.get(name,0)}")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
    except Exception as e:
        log.warning("feedstatus failed: %s", e)
        await update.message.reply_text("feedstatus error.")
    finally:
        try: db.close()
        except Exception: pass

# ===== build app =====
def build_application()->Application:
    token=(os.getenv("BOT_TOKEN") or "").strip()
    app=ApplicationBuilder().token(token).build()

    # Commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("selftest", selftest_cmd))
    app.add_handler(CommandHandler(["feedstatus","feedstats"], feedstatus_cmd))

    # Callback buttons
    app.add_handler(CallbackQueryHandler(job_buttons_cb, pattern=r"^job:(save|delete):"))
    app.add_handler(CallbackQueryHandler(menu_action_cb, pattern=r"^act:"))

    # (Όλα τα υπόλοιπα handlers σου – whoami, addkeyword, keywords, delkeyword,
    #  contact/admin chat, grant/block/unblock/broadcast – μένουν ως έχουν στο project)

    return app
