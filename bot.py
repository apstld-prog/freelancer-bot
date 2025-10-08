# bot.py
# -*- coding: utf-8 -*-
import os, logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple, Dict
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode

# DB wiring
SessionLocal=None; User=None; Keyword=None; Job=None; JobSent=None
try:
    from db import SessionLocal as _S, User as _U, Keyword as _K, Job as _J, JobSent as _JS, init_db as _init_db
    SessionLocal, User, Keyword, Job, JobSent = _S, _U, _K, _J, _JS
except Exception: pass

log=logging.getLogger("bot"); logging.basicConfig(level=os.getenv("LOG_LEVEL","INFO"))
UTC=timezone.utc
DEFAULT_TRIAL_DAYS=int(os.getenv("DEFAULT_TRIAL_DAYS","10"))

def now_utc(): return datetime.now(UTC)
def is_admin_id(tg_id:int)->bool:
    a=(os.getenv("ADMIN_ID") or "").strip()
    try: return str(tg_id)==str(int(a)) if a else False
    except Exception: return str(tg_id)==a
def db_ok(): return all([SessionLocal,User])

def _uid_field():
    for c in ("telegram_id","tg_id","chat_id","user_id","id"):
        if hasattr(User,c): return c
    raise RuntimeError("User id column not found")

# ----- UI helpers / texts (όπως έχουμε ήδη) -----
def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Keywords",callback_data="act:add"),
         InlineKeyboardButton("⚙️ Settings",callback_data="act:settings")],
        [InlineKeyboardButton("🆘 Help",callback_data="act:help"),
         InlineKeyboardButton("💾 Saved",callback_data="act:saved")],
        [InlineKeyboardButton("📞 Contact",callback_data="act:contact"),
         InlineKeyboardButton("👑 Admin",callback_data="act:admin")],
    ])

WELCOME_HEAD=("👋 <b>Welcome to Freelancer Alert Bot!</b>\n\n"
              "🎁 <b>You have a 10-day free trial.</b>\n"
              "Automatically finds matching freelance jobs from top\n"
              "platforms and sends you instant alerts.\n\n"
              "Use <code>/help</code> to see how it works.")
FEATURES_TEXT=("✨ <b>Features</b>\n"
               "• Realtime job alerts (Freelancer API)\n"
               "• Proposal & Original links (safe wrappers)\n"
               "• Budget shown + USD conversion\n"
               "• ⭐ Keep / 🗑️ Delete buttons\n"
               "• 10-day free trial, extend via admin\n"
               "• Multi-keyword search (single/all modes)\n"
               "• Platforms by country (incl. GR boards)")
HELP_TEXT=("🧭 <b>Help / How it works</b>\n\n"
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
           "➤ Use <code>/mysettings</code> anytime to check your filters and proposal.\n"
           "➤ <code>/selftest</code> for a test job.\n"
           "➤ <code>/platforms CC</code> to see platforms by country (e.g., <code>/platforms GR</code>).")

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
    active = "✅" if (not getattr(u,"is_blocked",False) and exp and exp>=now_utc()) else "❌"
    blocked= "✅" if getattr(u,"is_blocked",False) else "❌"
    kw = ", ".join(kws) if kws else "—"
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

async def start_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME_HEAD, reply_markup=main_kb(), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    if db_ok():
        db=SessionLocal()
        try:
            # ensure user exists (όπως πριν)
            u=db.query(User).filter(getattr(User,_uid_field())==str(update.effective_user.id)).one_or_none()
            if not u:
                u=User(telegram_id=str(update.effective_user.id), started_at=now_utc(), trial_until=now_utc()+timedelta(days=DEFAULT_TRIAL_DAYS), is_blocked=False)
                db.add(u); db.commit(); db.refresh(u)
            kws=[]
            try:
                rel=getattr(u,"keywords",None)
                if rel is not None:
                    for k in list(rel):
                        t=getattr(k,"keyword",None) or getattr(k,"text",None)
                        if t: kws.append(str(t))
            except Exception: pass
            await update.message.reply_text(settings_card(u,kws), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        finally: db.close()
    await update.message.reply_text(FEATURES_TEXT, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

# … (όλες οι υπόλοιπες εντολές/handlers όπως στο δικό σου bot.py παραμένουν ίδιες) …

# ---------- /feedstatus (JOIN με job) ----------
async def feedstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_id(update.effective_user.id):
        await update.message.reply_text("Admin only."); return
    if not all([SessionLocal, Job, JobSent]):
        await update.message.reply_text("DB not available."); return

    db = SessionLocal()
    try:
        since = now_utc() - timedelta(hours=24)
        rows = (db.query(Job.source)
                  .join(JobSent, JobSent.job_id == Job.id)
                  .filter(JobSent.created_at >= since)
                  .all())
        counts: Dict[str,int] = {}
        for (src,) in rows:
            counts[src] = counts.get(src, 0) + 1

        ordered = ["99designs","Careerjet","Codeable","Freelancer","Guru","JobFind","Kariera","Malt","PeoplePerHour",
                   "Skywalker","Toptal","Workana","Worksome","Wripple","YunoJuno","freelancermap","twago"]
        lines = ["📊 <b>Sent jobs by platform (last 24h)</b>"]
        for name in ordered:
            lines.append(f"• {name}: {counts.get(name,0)}")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
    except Exception as e:
        log.warning("feedstatus failed: %s", e)
        await update.message.reply_text("feedstatus error.")
    finally:
        try: db.close()
        except Exception: pass

# ---------- register ----------
def build_application()->Application:
    token=(os.getenv("BOT_TOKEN") or "").strip()
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start_cmd))
    # … βάλε εδώ τα υπόλοιπα handlers που ήδη έχεις (help, whoami, keywords, contact, admin, buttons, κ.λπ.) …
    app.add_handler(CommandHandler(["feedstatus","feedstats"], feedstatus_cmd))
    return app
