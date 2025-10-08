# bot.py
# -*- coding: utf-8 -*-
# ==========================================================
# ⚠️ UI_LOCKED: DO NOT MODIFY any text layout, menu, or job card
# ==========================================================
import os, logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, Application,
    CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, filters
)
from telegram.constants import ParseMode

# SQL text helper (for SQLAlchemy 2.x raw SQL)
try:
    from sqlalchemy import text as sql_text  # type: ignore
except Exception:
    sql_text = None

# === DB models ===
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
UI_LOCKED=True

def now_utc(): return datetime.now(UTC)
def is_admin_id(tg_id:int)->bool:
    adm=(os.getenv("ADMIN_ID") or "").strip()
    return str(tg_id)==str(adm) if adm else False
def admin_chat_id() -> Optional[int]:
    a=(os.getenv("ADMIN_ID") or "").strip()
    return int(a) if a.isdigit() else None
def _uid_field():
    for c in ("telegram_id","tg_id","chat_id","user_id","id"):
        if hasattr(User,c): return c
    raise RuntimeError("User id column not found")

# ----------------------------------------------------------
# MENU
# ----------------------------------------------------------
def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Keywords",callback_data="act:add"),
         InlineKeyboardButton("⚙️ Settings",callback_data="act:settings")],
        [InlineKeyboardButton("🆘 Help",callback_data="act:help"),
         InlineKeyboardButton("💾 Saved",callback_data="act:saved")],
        [InlineKeyboardButton("📞 Contact",callback_data="act:contact"),
         InlineKeyboardButton("Admin",callback_data="act:admin")],
    ])

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

async def _reply(update:Update, text:str, kb:InlineKeyboardMarkup|None=None, html:bool=False):
    msg = update.effective_message or update.message
    return await msg.reply_text(
        text,
        reply_markup=kb,
        disable_web_page_preview=True,
        parse_mode=ParseMode.HTML if html else None
    )

# ----------------------------------------------------------
# COMMANDS
# ----------------------------------------------------------
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

async def _send_saved_cards(update:Update, rows):
    for j in rows:
        kb=InlineKeyboardMarkup([
            [InlineKeyboardButton("📨 Proposal", url=j.proposal_url or j.original_url or j.url),
             InlineKeyboardButton("🔗 Original", url=j.original_url or j.url or j.proposal_url)],
            [InlineKeyboardButton("⭐ Save", callback_data=f"job:save:{j.id}"),
             InlineKeyboardButton("🗑️ Delete", callback_data=f"job:delete:{j.id}")],
        ])
        text = (
            f"{j.title or 'Untitled'}\n"
            + (f"🧾 Budget: {j.budget_min}–{j.budget_max} {j.budget_currency}\n" if j.budget_min or j.budget_max or j.budget_currency else "")
            + f"📎 Source: {j.source}\n"
            + (f"🔍 Match: {j.matched_keyword}\n" if getattr(j,'matched_keyword',None) else "")
            + (f"📝 {(j.description or '')[:1000]}\n" if j.description else "")
        ).rstrip()
        await _reply(update, text, kb)

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
        job_ids=[a.job_id for a in acts]
        rows=db.query(Job).filter(Job.id.in_(job_ids)).order_by(Job.id.desc()).all()
        if not rows:
            await _reply(update, "No saved jobs yet."); return
        await _send_saved_cards(update, rows)
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
            "SELECT LOWER(j.source) AS src, COUNT(*) AS cnt "
            "FROM job_sent s JOIN job j ON j.id=s.job_id "
            "WHERE s.created_at >= :since GROUP BY src ORDER BY src"
        )
        stmt = sql_text(sql) if sql_text else sql
        rows = list(db.execute(stmt, {"since": since}))
        title = "📊 Sent jobs by platform (last 24h)"
        if not rows:
            await _reply(update, f"{title}\n(0 results)"); return
        lines=[title] + [f"• {str(src).capitalize()}: {int(cnt)}" for src,cnt in rows]
        await _reply(update, "\n".join(lines))
    finally:
        try: db.close()
        except Exception: pass

# ----------------------------------------------------------
# CONTACT / ADMIN REPLY FLOW
# ----------------------------------------------------------
def _grant_days_in_db(tg_id: str, days: int) -> bool:
    if not (SessionLocal and User): return False
    ok=False
    db=SessionLocal()
    try:
        u=db.query(User).filter(getattr(User,_uid_field())==str(tg_id)).one_or_none()
        if not u: return False
        base=getattr(u,"access_until",None) or now_utc()
        new_until = (base if base>now_utc() else now_utc()) + timedelta(days=days)
        try:
            setattr(u,"access_until",new_until)
        except Exception:
            try: setattr(u,"license_until",new_until)
            except Exception: pass
        db.add(u); db.commit()
        ok=True
    except Exception:
        db.rollback()
    finally:
        try: db.close()
        except Exception: pass
    return ok

def _admin_contact_kb(tg_id:int)->InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Reply",   callback_data=f"adm:reply:{tg_id}")],
        [InlineKeyboardButton("❌ Decline", callback_data=f"adm:decline:{tg_id}")],
        [InlineKeyboardButton("+30d",  callback_data=f"adm:grant:{tg_id}:30"),
         InlineKeyboardButton("+90d",  callback_data=f"adm:grant:{tg_id}:90")],
        [InlineKeyboardButton("+180d", callback_data=f"adm:grant:{tg_id}:180"),
         InlineKeyboardButton("+365d", callback_data=f"adm:grant:{tg_id}:365")],
    ])

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
        context.user_data["contact_mode"]=True
        await q.message.reply_text("✍️ Type your message for the admin now. It will be forwarded.")
    elif act=="admin":
        if is_admin_id(q.from_user.id):
            txt = (
                "Admin panel:\n"
                "• /users — list users\n"
                "• /grant <id> <days> — extend license\n"
                "• /block <id> — block user\n"
                "• /unblock <id> — unblock user\n"
                "• /feedstatus — show last 24h by platform"
            )
            await q.message.reply_text(txt, disable_web_page_preview=True)
        else:
            await q.message.reply_text("Admin only.")
    await q.answer()

async def inbound_text_handler(update:Update, context:ContextTypes.DEFAULT_TYPE):
    msg=update.effective_message
    user=update.effective_user
    admin_id = admin_chat_id()

    # 1) User contacting admin
    if context.user_data.get("contact_mode"):
        context.user_data["contact_mode"]=False
        if not admin_id:
            await msg.reply_text("Admin is not available right now.")
            return
        text=f"📩 New message from user\nID: <code>{user.id}</code>\n\n{msg.text}"
        await context.bot.send_message(chat_id=admin_id, text=text, parse_mode=ParseMode.HTML,
                                       reply_markup=_admin_contact_kb(user.id))
        await msg.reply_text("✅ Your message was sent to the admin. You'll receive the reply here.")
        return

    # 2) Admin typing a reply
    if is_admin_id(user.id) and context.user_data.get("admin_reply_to"):
        target_id=context.user_data.get("admin_reply_to")
        await context.bot.send_message(chat_id=int(target_id), text=f"👑 Admin:\n{msg.text}")
        await msg.reply_text("✅ Your reply was sent to the user.")
        context.user_data["admin_reply_to"]=None
        return

async def admin_actions_cb(update:Update, context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    if not q: return
    if not is_admin_id(q.from_user.id):
        await q.answer("Admin only."); return
    data=(q.data or "")
    parts=data.split(":")
    # patterns: adm:reply:<uid> | adm:decline:<uid> | adm:grant:<uid>:<days>
    if len(parts)>=3 and parts[0]=="adm":
        action=parts[1]
        uid=parts[2]
        if action=="reply":
            context.user_data["admin_reply_to"]=uid
            await q.message.reply_text(f"✍️ Type your reply for user {uid}…")
            await q.answer("Reply mode on")
        elif action=="decline":
            try:
                await context.bot.send_message(chat_id=int(uid), text="❌ The admin declined the request. You may contact again later.")
            except Exception: pass
            await q.answer("Declined")
        elif action=="grant" and len(parts)==4:
            days=int(parts[3])
            ok=_grant_days_in_db(uid, days)
            if ok:
                await q.message.reply_text(f"✅ Added {days} days of access for user {uid}.")
                try:
                    await context.bot.send_message(chat_id=int(uid), text=f"🎉 Your access has been extended by {days} days.")
                except Exception: pass
            else:
                await q.message.reply_text(f"ℹ️ DB update failed. Only a notification was sent.")
            await q.answer("OK")
    else:
        await q.answer()

# ----------------------------------------------------------
# JOB BUTTONS (Save/Delete)
# ----------------------------------------------------------
def _find_or_create_user(db, tg_id:str):
    u=db.query(User).filter(getattr(User,_uid_field())==str(tg_id)).one_or_none()
    if not u:
        u=User(telegram_id=str(tg_id), started_at=now_utc(),
               trial_until=now_utc()+timedelta(days=DEFAULT_TRIAL_DAYS),
               is_blocked=False)
        db.add(u); db.commit(); db.refresh(u)
    return u

async def job_buttons_cb(update:Update, context:ContextTypes.DEFAULT_TYPE):
    """Callback for job card buttons: Save / Delete."""
    q=update.callback_query
    if not q: return
    data=q.data or ""
    # pattern: job:save:<job_id> or job:delete:<job_id>
    parts=data.split(":")
    if len(parts)!=3:
        await q.answer(); return
    action, job_id = parts[1], parts[2]

    if not all([SessionLocal, User, JobAction]):
        # DB not available -> UI-only feedback
        if action=="delete":
            try: await context.bot.delete_message(chat_id=q.message.chat_id, message_id=q.message.message_id)
            except Exception: pass
        else:
            await q.answer("Saved (no DB)")
        return

    db=SessionLocal()
    try:
        u=_find_or_create_user(db, str(q.from_user.id))

        # store action
        try:
            ja=JobAction(user_id=u.id, job_id=int(job_id) if job_id.isdigit() else job_id,
                         action=("save" if action=="save" else "delete"),
                         created_at=now_utc())
            db.add(ja); db.commit()
        except Exception:
            db.rollback()

        if action=="delete":
            # remove card from chat
            try:
                await context.bot.delete_message(chat_id=q.message.chat_id, message_id=q.message.message_id)
            except Exception:
                try: await q.edit_message_reply_markup(reply_markup=None)
                except Exception: pass
            await q.answer("Deleted")
        else:
            # Save: notify + hide card (as requested)
            try:
                await context.bot.delete_message(chat_id=q.message.chat_id, message_id=q.message.message_id)
            except Exception:
                try: await q.edit_message_reply_markup(reply_markup=None)
                except Exception: pass
            await _reply(update, "⭐ Saved.")
            await q.answer("Saved")
    finally:
        try: db.close()
        except Exception: pass

# ----------------------------------------------------------
# ADMIN
# ----------------------------------------------------------
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
    arg=" ".join(context.args).strip().upper() if context.args else ""
    global_list = (
        "Global: Freelancer.com, PeoplePerHour, Malt, Workana, Guru, 99designs, "
        "Toptal*, Codeable*, YunoJuno*, Worksome*, Wripple, twago, freelancermap, Careerjet "
        "(*referral/curated)"
    )
    gr_list = "Greece: JobFind.gr, Skywalker.gr, Kariera.gr"
    if not arg:
        await _reply(update, "Usage: /platforms ALL | GLOBAL | GR")
        return
    if arg in ("ALL","*"):
        await _reply(update, f"{global_list}\n\n{gr_list}")
    elif arg in ("GLOBAL","INT"):
        await _reply(update, global_list)
    elif arg=="GR":
        await _reply(update, gr_list)
    else:
        await _reply(update, "Usage: /platforms ALL | GLOBAL | GR")

async def selftest_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    kb=InlineKeyboardMarkup([
        [InlineKeyboardButton("📨 Proposal", url="https://www.freelancer.com"),
         InlineKeyboardButton("🔗 Original", url="https://www.freelancer.com")],
        [InlineKeyboardButton("⭐ Save", callback_data="job:save:999999"),
         InlineKeyboardButton("🗑️ Delete", callback_data="job:delete:999999")],
    ])
    await _reply(update,
        "Logo Reformatting to SVG\n"
        "🧾 Budget: 30.0–250.0 AUD (~$20–$163)\n"
        "📎 Source: Freelancer\n"
        "🔍 Match: <b><u>logo</u></b>\n"
        "📝 I need my existing logo reformatted into SVG... (sample)\n"
        "⏱️ 2m ago",
        kb,
        html=True
    )

def build_application()->Application:
    if '_init_db' in globals() and callable(_init_db):
        try: _init_db()
        except Exception: pass

    token=(os.getenv("BOT_TOKEN") or "").strip()
    app=ApplicationBuilder().token(token).build()

    # commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))
    app.add_handler(CommandHandler("saved", saved_cmd))
    app.add_handler(CommandHandler("feedstatus", feedstatus_cmd))
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CommandHandler("platforms", platforms_cmd))
    app.add_handler(CommandHandler("selftest", selftest_cmd))

    # callbacks
    app.add_handler(CallbackQueryHandler(job_buttons_cb, pattern=r"^job:(save|delete):"))
    app.add_handler(CallbackQueryHandler(menu_action_cb, pattern=r"^act:"))
    app.add_handler(CallbackQueryHandler(admin_actions_cb, pattern=r"^adm:"))

    # free text (for Contact and Admin replies)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, inbound_text_handler))
    return app
