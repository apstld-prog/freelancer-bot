# bot.py
# -*- coding: utf-8 -*-
"""
Freelancer Alert Bot
python-telegram-bot v20+

- Welcome + big menu
- Keywords: /addkeyword, /keywords, /delkeyword
- Admin: /users, /grant <telegram_id> <days>, /block, /unblock, /broadcast <text>, /feedstatus
- Contact (two-way chat) with Reply/Decline on BOTH sides, chat stays open until Decline
- Quick grant buttons: +30d, +90d, +180d, +365d
- Daily reminder 24h before expiration
- Works with your db.py schema (telegram_id, started_at, trial_until, access_until, is_blocked)
"""

import os
import logging
from math import ceil
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)
from telegram.constants import ParseMode

# ---------- DB (defensive import) ----------
SessionLocal = None; User = None; Keyword = None; JobSent = None
try:
    from db import SessionLocal as _S, User as _U, Keyword as _K, JobSent as _J, init_db as _init_db
    SessionLocal, User, Keyword, JobSent = _S, _U, _K, _J
except Exception:
    pass

log = logging.getLogger("bot")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
UTC = timezone.utc

# ---------- ENV ----------
DEFAULT_TRIAL_DAYS = int(os.getenv("DEFAULT_TRIAL_DAYS", "10"))
ADMIN_CONTACT_TEXT = os.getenv("ADMIN_CONTACT_TEXT", "Contact the admin via this chat.")
QUICK_GRANTS = [30, 90, 180, 365]

# ---------- Helpers ----------
def now_utc() -> datetime: return datetime.now(UTC)
def is_admin_id(tg_id: int) -> bool:
    admin_id = (os.getenv("ADMIN_ID") or "").strip()
    if not admin_id: return False
    try: return str(tg_id) == str(int(admin_id))
    except Exception: return str(tg_id) == admin_id
def is_admin(update: Update) -> bool: return is_admin_id(update.effective_user.id)
def db_available() -> bool: return all([SessionLocal, User])

def _get_user_id_field() -> str:
    for cand in ("telegram_id","tg_id","chat_id","user_id","id"):
        if hasattr(User, cand): return cand
    raise RuntimeError("User model must expose a telegram id field.")

def _user_lookup(db, tg_id: int):
    uf = _get_user_id_field(); col = getattr(User, uf)
    try: is_str = col.property.columns[0].type.python_type is str  # type: ignore
    except Exception: is_str = False
    return db.query(User).filter(col == (str(tg_id) if is_str else tg_id)).one_or_none()

def _get_or_create_user(db, tg_id: int):
    u = _user_lookup(db, tg_id)
    if u:
        if hasattr(u, "started_at") and not getattr(u, "started_at"):
            setattr(u, "started_at", now_utc())
        if hasattr(u, "trial_until") and not getattr(u, "trial_until"):
            setattr(u, "trial_until", now_utc() + timedelta(days=DEFAULT_TRIAL_DAYS))
        db.commit(); return u

    uf = _get_user_id_field()
    u = User()
    try: setattr(u, uf, tg_id)
    except Exception: setattr(u, uf, str(tg_id))
    if hasattr(u, "started_at"):  setattr(u, "started_at", now_utc())
    if hasattr(u, "trial_until"): setattr(u, "trial_until", now_utc() + timedelta(days=DEFAULT_TRIAL_DAYS))
    if hasattr(u, "is_blocked"):  setattr(u, "is_blocked", False)
    if hasattr(u, "created_at") and not getattr(u, "created_at", None):
        setattr(u, "created_at", now_utc())
    db.add(u); db.commit(); db.refresh(u); return u

def _list_keywords(db, user) -> List['Keyword']:
    if Keyword is None: return []
    try:
        if hasattr(user, "keywords") and getattr(user, "keywords") is not None:
            return list(getattr(user, "keywords"))
    except Exception:
        pass
    q = None
    uid = None
    for uf in ("id","user_id","pk"):
        if hasattr(user, uf): uid = getattr(user, uf); break
    for kf in ("user_id","uid","owner_id"):
        if hasattr(Keyword, kf): q = db.query(Keyword).filter(getattr(Keyword, kf) == uid); break
    return list(q.all()) if q is not None else []

def _disp_id(u) -> str:
    for f in ("telegram_id","tg_id","chat_id","user_id","id","pk"):
        if hasattr(u, f): return str(getattr(u, f))
    return "?"

def _dates_for_user(u) -> Tuple[Optional[datetime], Optional[datetime], Optional[datetime]]:
    trial_start = getattr(u, "started_at", None) or getattr(u, "trial_start", None)
    trial_ends  = getattr(u, "trial_until", None) or getattr(u, "trial_ends", None)
    license_until = getattr(u, "access_until", None) or getattr(u, "license_until", None)
    return trial_start, trial_ends, license_until

def _effective_expiry(u) -> Optional[datetime]:
    _, te, lu = _dates_for_user(u)
    return lu or te

def _fmt(dt: Optional[datetime]) -> str:
    if not dt: return "None"
    try: return dt.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%SZ")
    except Exception: return str(dt)

def _days_remaining(exp: Optional[datetime]) -> str:
    if not exp: return "—"
    try: delta = exp.astimezone(UTC) - now_utc()
    except Exception: delta = exp - now_utc()
    secs = delta.total_seconds()
    if secs < 0: return f"expired {ceil(abs(secs)/86400)} day(s) ago"
    return f"in {ceil(secs/86400)} day(s)"

def _active_blocked(u) -> Tuple[str, str]:
    blocked = "✅" if getattr(u, "is_blocked", False) else "❌"
    exp = _effective_expiry(u)
    active_flag = (not getattr(u, "is_blocked", False)) and bool(exp and exp >= now_utc())
    active = "✅" if active_flag else "❌"
    return active, blocked

def _extend_days(dt0: Optional[datetime], days: int) -> datetime:
    base = dt0 if dt0 and dt0 > now_utc() else now_utc()
    return base + timedelta(days=days)

# ---------- UI ----------
def main_menu_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("➕ Add Keywords", callback_data="act:add"),
         InlineKeyboardButton("⚙️ Settings",   callback_data="act:settings")],
        [InlineKeyboardButton("🆘 Help",        callback_data="act:help"),
         InlineKeyboardButton("💾 Saved",       callback_data="act:saved")],
        [InlineKeyboardButton("📞 Contact",     callback_data="act:contact"),
         InlineKeyboardButton("👑 Admin",       callback_data="act:admin")],
    ]
    return InlineKeyboardMarkup(rows)

WELCOME_HEAD = (
    "👋 <b>Welcome to Freelancer Alert Bot!</b>\n\n"
    "🎁 <b>You have a 10-day free trial.</b>\n"
    "Automatically finds matching freelance jobs from top\n"
    "platforms and sends you instant alerts.\n\n"
    "Use <code>/help</code> to see how it works."
)

FEATURES_TEXT = (
    "✨ <b>Features</b>\n"
    "• Realtime job alerts (Freelancer API)\n"
    "• Proposal & Original links (safe wrappers)\n"
    "• Budget shown + USD conversion\n"
    "• ⭐ Keep / 🗑️ Delete buttons\n"
    "• 10-day free trial, extend via admin\n"
    "• Multi-keyword search (single/all modes)\n"
    "• Platforms by country (incl. GR boards)"
)

HELP_TEXT = (
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
    "➤ Use <code>/mysettings</code> anytime to check your filters and proposal.\n"
    "➤ <code>/selftest</code> for a test job.\n"
    "➤ <code>/platforms CC</code> to see platforms by country (e.g., <code>/platforms GR</code>).\n\n"
    "📋 <b>Platforms monitored</b>:\n"
    "• Global: Freelancer.com, PeoplePerHour, Malt, Workana, Guru, 99designs, Toptal*, Codeable*, YunoJuno*, "
    "Worksome*, twago, freelancermap (* referral/curated platforms)\n"
    "• Greece: JobFind.gr, Skywalker.gr, Kariera.gr\n\n"
    "👑 <b>Admin commands</b>\n"
    "<code>/users</code> — list users\n"
    "<code>/grant &lt;telegram_id&gt; &lt;days&gt;</code> — extend license\n"
    "<code>/block &lt;telegram_id&gt;</code> / <code>/unblock &lt;telegram_id&gt;</code>\n"
    "<code>/broadcast &lt;text&gt;</code> — send message to all active\n"
    "<code>/feedstatus</code> — per-platform counters (24h)\n"
)

def settings_card_text(u, kws: List[str]) -> str:
    ts, te, lu = _dates_for_user(u)
    active, blocked = _active_blocked(u)
    kw_display = ", ".join(kws) if kws else "—"
    exp = _effective_expiry(u)
    return (
        "🛠️ <b>Your Settings</b>\n"
        f"• Keywords: {kw_display}\n"
        "• Countries: ALL\n"
        "• Proposal template: (none)\n\n"
        f"🟢 Trial start: {_fmt(ts)}\n"
        f"⏳ Trial ends: {_fmt(te)}\n"
        f"🔑 License until: {_fmt(lu)}\n"
        f"📅 <b>Expires:</b> {_fmt(exp)} ({_days_remaining(exp)})\n"
        f"🟢 Active: {active}\n"
        f"⛔ Blocked: {blocked}\n\n"
        "📜 Platforms monitored:\n"
        "Freelancer.com, PeoplePerHour, Malt, Workana, Guru, 99designs, Toptal*, Codeable*, YunoJuno*, Worksome*, "
        "twago, freelancermap\n"
        "(* referral/curated platforms)\n\n"
        "Greece: JobFind.gr, Skywalker.gr, Kariera.gr\n\n"
        "When your trial ends, please <b>contact the admin</b> to extend your access."
    )

# ---------- Send helper ----------
async def _send_html(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    chat_id = update.effective_chat.id if update.effective_chat else None
    if chat_id is not None:
        await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML,
                                       disable_web_page_preview=True)

# ---------- Commands ----------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME_HEAD, reply_markup=main_menu_keyboard(),
                                    parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    if db_available():
        db = SessionLocal()
        try:
            u = _get_or_create_user(db, update.effective_user.id)
            kws = [getattr(k, "keyword", None) or getattr(k, "text", None) or "" for k in _list_keywords(db, u)]
            await update.message.reply_text(settings_card_text(u, kws), parse_mode=ParseMode.HTML,
                                            disable_web_page_preview=True)
        finally:
            db.close()
    await update.message.reply_text(FEATURES_TEXT, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_html(update, context, HELP_TEXT)

async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    role = "Admin" if is_admin(update) else "User"
    uname = update.effective_user.username
    text = f"🆔 Your ID: <code>{uid}</code>\nRole: <b>{role}</b>"
    if uname: text += f"\n@{uname}"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def addkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: <code>/addkeyword &lt;word&gt;</code>", parse_mode=ParseMode.HTML); return
    word = " ".join(context.args).strip()
    if not db_available():
        await update.message.reply_text(f"(demo) ✅ Added keyword: <code>{word}</code> (no DB)", parse_mode=ParseMode.HTML); return
    db = SessionLocal()
    try:
        u = _get_or_create_user(db, update.effective_user.id)
        k = Keyword()
        if hasattr(k, "keyword"): setattr(k, "keyword", word)
        elif hasattr(k, "text"):  setattr(k, "text", word)
        if hasattr(k, "user"): setattr(k, "user", u)
        elif hasattr(k, "user_id"): setattr(k, "user_id", getattr(u, "id", None))
        db.add(k); db.commit(); db.refresh(k)
        await update.message.reply_text(f"✅ Added keyword: <code>{word}</code>", parse_mode=ParseMode.HTML)
    finally: db.close()

async def keywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not db_available():
        await update.message.reply_text("(demo) DB is not available here."); return
    db = SessionLocal()
    try:
        u = _get_or_create_user(db, update.effective_user.id)
        kws = _list_keywords(db, u)
        shown=[]
        if kws:
            lines=["📃 <b>Your keywords</b>"]
            for k in kws:
                text = getattr(k, "keyword", None) or getattr(k, "text", None) or ""
                kid  = getattr(k, "id", None)
                shown.append(text)
                lines.append(f"• <code>{kid}</code> — {text}")
            await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text("You have no keywords yet. Add one with <code>/addkeyword ...</code>",
                                            parse_mode=ParseMode.HTML)
        await update.message.reply_text(settings_card_text(u, shown), parse_mode=ParseMode.HTML,
                                        disable_web_page_preview=True)
    finally: db.close()

async def delkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: <code>/delkeyword &lt;word&gt;</code> or <code>/delkeyword &lt;id&gt;</code>",
                                        parse_mode=ParseMode.HTML); return
    ident = " ".join(context.args).strip()
    if not db_available():
        await update.message.reply_text(f"(demo) ✅ Deleted: <code>{ident}</code> (no DB)", parse_mode=ParseMode.HTML); return
    db = SessionLocal()
    try:
        u = _get_or_create_user(db, update.effective_user.id)
        deleted = 0
        try:
            kid = int(ident)
            q = db.query(Keyword).filter(Keyword.user_id == getattr(u, "id"))
            if hasattr(Keyword, "id"): q = q.filter(Keyword.id == kid)
            for row in q.all(): db.delete(row); deleted += 1
            db.commit()
        except Exception:
            q = db.query(Keyword).filter(Keyword.user_id == getattr(u, "id"))
            fld = "keyword" if hasattr(Keyword, "keyword") else "text"
            for row in q.filter(getattr(Keyword, fld) == ident).all():
                db.delete(row); deleted += 1
            db.commit()
        await update.message.reply_text(f"🗑️ Deleted {deleted} keyword(s) for <code>{ident}</code>", parse_mode=ParseMode.HTML)
    finally: db.close()

# ---------- Contact (two-way) ----------
def admin_contact_kb(user_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("💬 Reply",   callback_data=f"admchat:reply:{user_id}")],
        [InlineKeyboardButton("❌ Decline", callback_data=f"admchat:decline:{user_id}")],
        [InlineKeyboardButton("➕ +30d",  callback_data=f"adm:grant:{user_id}:30"),
         InlineKeyboardButton("➕ +90d",  callback_data=f"adm:grant:{user_id}:90")],
        [InlineKeyboardButton("➕ +180d", callback_data=f"adm:grant:{user_id}:180"),
         InlineKeyboardButton("➕ +365d", callback_data=f"adm:grant:{user_id}:365")],
    ]
    return InlineKeyboardMarkup(rows)

def user_reply_kb(admin_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("💬 Reply",   callback_data=f"usrchat:reply:{admin_id}")],
        [InlineKeyboardButton("❌ Decline", callback_data="usrchat:decline")],
    ]
    return InlineKeyboardMarkup(rows)

async def contact_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q: return
    await q.answer()
    context.user_data["awaiting_contact_msg"] = True
    await q.message.reply_text("✍️ Send me your message and I’ll forward it to the admin.")

async def capture_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    uid = update.effective_user.id
    admin_id_env = os.getenv("ADMIN_ID")

    if is_admin(update):
        target = context.application.bot_data.get("admin_reply_target", {}).get(uid)
        if target:
            try:
                await context.bot.send_message(chat_id=target, text=f"📨 Admin:\n{text}",
                                               reply_markup=user_reply_kb(uid))
                await update.message.reply_text("✅ Sent to user.")
            finally:
                pass
            return

    if context.user_data.get("awaiting_contact_msg"):
        context.user_data["awaiting_contact_msg"] = False
        if not admin_id_env:
            await update.message.reply_text("Admin is not configured."); return
        msg = f"📥 <b>New message from user</b>\nID: <code>{uid}</code>\n\n{text}"
        await context.bot.send_message(chat_id=int(admin_id_env), text=msg, parse_mode=ParseMode.HTML,
                                       reply_markup=admin_contact_kb(uid))
        await update.message.reply_text("✅ Sent to admin. You’ll receive a reply soon.")
        context.application.bot_data.setdefault("user_reply_target", {})[uid] = int(admin_id_env)
        return

    target_admin = context.application.bot_data.get("user_reply_target", {}).get(uid)
    if target_admin:
        try:
            await context.bot.send_message(chat_id=target_admin, text=f"📨 User {uid}:\n{text}",
                                           reply_markup=admin_contact_kb(uid))
            await update.message.reply_text("✅ Sent to admin.")
        finally:
            pass

# ---------- Admin & Grants ----------
def _list_all_users(db) -> List[User]:
    try: return list(db.query(User).all())
    except Exception: return []

async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): await update.message.reply_text("Admin only."); return
    if not db_available():   await update.message.reply_text("DB not available."); return
    db = SessionLocal()
    try:
        users = _list_all_users(db)
        lines=["👥 <b>Users</b>"]
        for u in users[:200]:
            kws=_list_keywords(db,u)
            ts,te,lu=_dates_for_user(u)
            exp=_effective_expiry(u)
            a,b=_active_blocked(u)
            lines.append(
                f"• <code>{_disp_id(u)}</code> — kw:{len(kws)} | "
                f"trial:{_fmt(ts)}→{_fmt(te)} | lic:{_fmt(lu)} | "
                f"Expires:{_fmt(exp)} ({_days_remaining(exp)}) | A:{a} B:{b}"
            )
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    finally: db.close()

async def _do_grant(update: Update, context: ContextTypes.DEFAULT_TYPE, target_id: int, days: int):
    db=SessionLocal()
    try:
        u=_user_lookup(db, target_id)
        if not u: await update.message.reply_text("User not found."); return
        cur = getattr(u, "access_until", None) or getattr(u, "trial_until", None)
        if hasattr(u, "access_until"):
            setattr(u, "access_until", _extend_days(cur, days))
        elif hasattr(u, "license_until"):
            setattr(u, "license_until", _extend_days(cur, days))
        elif hasattr(u, "trial_until"):
            setattr(u, "trial_until", _extend_days(cur, days))
        if hasattr(u, "is_blocked"): setattr(u, "is_blocked", False)
        db.commit()
        ts, te, lu = _dates_for_user(u)
        await update.message.reply_text(
            "✅ Granted access.\n"
            f"user: <code>{_disp_id(u)}</code>\n"
            f"trial: {_fmt(ts)} → {_fmt(te)}\n"
            f"license/access: {_fmt(lu)}", parse_mode=ParseMode.HTML
        )
        try:
            await context.bot.send_message(chat_id=target_id, text=f"✅ Your access was extended by {days} day(s).",
                                           reply_markup=user_reply_kb(int(os.getenv('ADMIN_ID') or 0)))
        except Exception: pass
    finally:
        db.close()

async def grant_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): await update.message.reply_text("Admin only."); return
    if len(context.args)<2:
        await update.message.reply_text("Usage: <code>/grant &lt;telegram_id&gt; &lt;days&gt;</code>", parse_mode=ParseMode.HTML); return
    if not db_available(): await update.message.reply_text("DB not available."); return
    try: target_id=int(context.args[0]); days=int(context.args[1])
    except Exception:
        await update.message.reply_text("Usage: <code>/grant &lt;telegram_id&gt; &lt;days&gt;</code>", parse_mode=ParseMode.HTML); return
    await _do_grant(update, context, target_id, days)

async def block_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): await update.message.reply_text("Admin only."); return
    if not context.args: await update.message.reply_text("Usage: <code>/block &lt;telegram_id&gt;</code>", parse_mode=ParseMode.HTML); return
    if not db_available(): await update.message.reply_text("DB not available."); return
    try: target_id=int(context.args[0])
    except Exception:
        await update.message.reply_text("Usage: <code>/block &lt;telegram_id&gt;</code>", parse_mode=ParseMode.HTML); return
    db=SessionLocal()
    try:
        u=_user_lookup(db,target_id)
        if not u: await update.message.reply_text("User not found."); return
        if hasattr(u,"is_blocked"): setattr(u,"is_blocked", True)
        db.commit(); await update.message.reply_text("✅ User blocked.")
    finally: db.close()

async def unblock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): await update.message.reply_text("Admin only."); return
    if not context.args: await update.message.reply_text("Usage: <code>/unblock &lt;telegram_id&gt;</code>", parse_mode=ParseMode.HTML); return
    if not db_available(): await update.message.reply_text("DB not available."); return
    try: target_id=int(context.args[0])
    except Exception:
        await update.message.reply_text("Usage: <code>/unblock &lt;telegram_id&gt;</code>", parse_mode=ParseMode.HTML); return
    db=SessionLocal()
    try:
        u=_user_lookup(db,target_id)
        if not u: await update.message.reply_text("User not found."); return
        if hasattr(u,"is_blocked"): setattr(u,"is_blocked", False)
        db.commit(); await update.message.reply_text("✅ User unblocked.")
    finally: db.close()

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): await update.message.reply_text("Admin only."); return
    msg=" ".join(context.args).strip()
    if not msg: await update.message.reply_text("Usage: <code>/broadcast &lt;text&gt;</code>", parse_mode=ParseMode.HTML); return
    if not db_available(): await update.message.reply_text("DB not available."); return

    from httpx import AsyncClient
    token=(os.getenv("BOT_TOKEN") or "").strip()
    api=f"https://api.telegram.org/bot{token}/sendMessage"
    db=SessionLocal(); sent=0
    try:
        users=_list_all_users(db)
        async with AsyncClient(timeout=float(os.getenv("HTTP_TIMEOUT","20"))) as client:
            for u in users:
                if getattr(u,"is_blocked", False): continue
                chat_id=None
                for f in ("chat_id","telegram_id","tg_id","user_id","id"):
                    if hasattr(u,f): chat_id=getattr(u,f); break
                if not chat_id: continue
                try:
                    await client.post(api, json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML",
                                                 "disable_web_page_preview": True})
                    sent+=1
                except Exception: pass
        await update.message.reply_text(f"📣 Broadcast sent to {sent} users.")
    finally: db.close()

# ---------- FIXED feedstatus ----------
async def feedstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("Admin only.")
        return

    known = [
        "99designs","Careerjet","Codeable","Freelancer","Guru","JobFind",
        "Kariera","Malt","PeoplePerHour","Skywalker","Toptal","Workana",
        "Worksome","Wripple","YunoJuno","freelancermap","twago"
    ]
    counters: Dict[str,int] = {k:0 for k in known}

    prefix_map = {
        "freelancer":"Freelancer", "pph":"PeoplePerHour", "malt":"Malt",
        "workana":"Workana", "guru":"Guru", "99designs":"99designs",
        "toptal":"Toptal", "codeable":"Codeable", "yuno_juno":"YunoJuno",
        "worksome":"Worksome", "twago":"twago", "freelancermap":"freelancermap",
        "wripple":"Wripple", "jobfind":"JobFind", "sky":"Skywalker",
        "kariera":"Kariera", "careerjet":"Careerjet"
    }

    used_db = False
    if SessionLocal and JobSent:
        db = SessionLocal()
        try:
            since = now_utc() - timedelta(hours=24)
            rows = db.query(JobSent).filter(JobSent.created_at >= since).all()
            for r in rows:
                label = None

                # 1) αν υπάρχει explicit source
                src = getattr(r, "source", None)
                if src:
                    lbl = prefix_map.get(str(src).strip().lower())
                    if lbl: label = lbl

                # 2) αλλιώς από job_id prefix (CAST σε str -> strip)
                if not label:
                    jid = str(getattr(r, "job_id", "") or "").strip()
                    pref = jid.split("-", 1)[0].lower() if "-" in jid else jid.lower()
                    label = prefix_map.get(pref)

                if label:
                    counters[label] = counters.get(label, 0) + 1

            used_db = True
        except Exception as e:
            log.warning("feedstatus query failed: %s", e)
        finally:
            try: db.close()
            except Exception: pass

    title = "📊 <b>Sent jobs by platform (last 24h)</b>"
    if not used_db:
        title += "\n<i>(DB not available — showing zeros)</i>"

    lines = [title] + [f"• {src}: {counters.get(src,0)}" for src in known]
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

# ---------- Callback router ----------
async def button_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    if not q: return
    data=q.data or ""
    await q.answer()

    if   data=="act:add":      await q.message.reply_text("Add a keyword with: <code>/addkeyword lighting</code>", parse_mode=ParseMode.HTML)
    elif data=="act:settings":
        if not db_available(): await q.message.reply_text("(demo) DB not available."); return
        db=SessionLocal()
        try:
            u=_get_or_create_user(db, q.from_user.id)
            kws=[getattr(k,"keyword",None) or getattr(k,"text",None) or "" for k in _list_keywords(db,u)]
            await q.message.reply_text(settings_card_text(u, kws), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        finally: db.close()
    elif data=="act:help":     await _send_html(update, context, HELP_TEXT)
    elif data=="act:saved":    await q.message.reply_text("Saved items will appear here (coming soon).")
    elif data=="act:contact":  await contact_button(update, context)
    elif data=="act:admin":
        if not is_admin_id(q.from_user.id): await q.message.reply_text("Admin only.")
        else:
            await _send_html(update, context,
                "Admin commands:\n"
                "<code>/users</code>\n"
                "<code>/grant &lt;telegram_id&gt; &lt;days&gt;</code>\n"
                "<code>/block &lt;telegram_id&gt;</code> / <code>/unblock &lt;telegram_id&gt;</code>\n"
                "<code>/broadcast &lt;text&gt;</code>\n"
                "<code>/feedstatus</code>"
            )

    elif data.startswith("admchat:reply:") and is_admin_id(q.from_user.id):
        user_id = int(data.split(":")[-1])
        context.application.bot_data.setdefault("admin_reply_target", {})[q.from_user.id] = user_id
        await q.message.reply_text(f"💬 Reply mode ON for user {user_id}. Send your message now.")
    elif data.startswith("admchat:decline:") and is_admin_id(q.from_user.id):
        user_id = int(data.split(":")[-1])
        try: await context.bot.send_message(chat_id=user_id, text="❌ Your request was declined by the admin.")
        except Exception: pass
        context.application.bot_data.get("admin_reply_target", {}).pop(q.from_user.id, None)
        context.application.bot_data.get("user_reply_target", {}).pop(user_id, None)
        await q.message.reply_text(f"Declined user {user_id}.")
    elif data.startswith("adm:grant:") and is_admin_id(q.from_user.id):
        _,_,uid,days = data.split(":"); await _do_grant(update, context, int(uid), int(days))

    elif data.startswith("usrchat:reply:"):
        admin_id = int(data.split(":")[-1])
        context.application.bot_data.setdefault("user_reply_target", {})[q.from_user.id] = admin_id
        await q.message.reply_text("💬 Reply mode ON. Send your message now.")
    elif data == "usrchat:decline":
        uid = q.from_user.id
        admin_id = context.application.bot_data.get("user_reply_target", {}).pop(uid, None)
        if admin_id:
            context.application.bot_data.get("admin_reply_target", {}).pop(admin_id, None)
        await q.message.reply_text("✅ Conversation closed.")

# ---------- Reminder job ----------
async def check_expirations(context: ContextTypes.DEFAULT_TYPE):
    if not db_available(): return
    admin_id_env=os.getenv("ADMIN_ID")
    db=SessionLocal(); now=now_utc(); in_24h=now+timedelta(hours=24)
    try:
        users=_list_all_users(db)
        for u in users:
            if getattr(u,"is_blocked", False): continue
            exp=_effective_expiry(u)
            if not exp: continue
            try: exp_utc=exp.astimezone(UTC)
            except Exception: exp_utc=exp
            if now <= exp_utc <= in_24h:
                chat_id = getattr(u, _get_user_id_field(), None)
                if chat_id:
                    try:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=f"⏳ Reminder: your access expires on <b>{_fmt(exp_utc)}</b> ({_days_remaining(exp_utc)}). "
                                 f"Use the Contact button to reach the admin.",
                            parse_mode=ParseMode.HTML
                        )
                    except Exception: pass
                if admin_id_env:
                    try:
                        await context.bot.send_message(
                            chat_id=int(admin_id_env),
                            text=f"⏳ User <code>{_disp_id(u)}</code> expires on <b>{_fmt(exp_utc)}</b> ({_days_remaining(exp_utc)}).",
                            parse_mode=ParseMode.HTML
                        )
                    except Exception: pass
    finally: db.close()

# ---------- Application ----------
async def _post_init(app: Application):
    try:
        if '_init_db' in globals() and callable(_init_db):
            _init_db()
            log.info("DB schema ensured on startup.")
    except Exception as e:
        log.warning("init_db() failed: %s", e)
    try:
        app.job_queue.run_repeating(check_expirations, interval=24*3600, first=60)
        log.info("Expiration reminder scheduled.")
    except Exception as e:
        log.warning("Could not schedule reminder: %s", e)

def build_application() -> Application:
    token=(os.getenv("BOT_TOKEN") or "").strip()
    if not token: raise RuntimeError("BOT_TOKEN is not set.")
    app_ = ApplicationBuilder().token(token).post_init(_post_init).build()

    # user
    app_.add_handler(CommandHandler("start", start_cmd))
    app_.add_handler(CommandHandler("help", help_cmd))
    app_.add_handler(CommandHandler("whoami", whoami_cmd))
    app_.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app_.add_handler(CommandHandler("keywords", keywords_cmd))
    app_.add_handler(CommandHandler("delkeyword", delkeyword_cmd))

    # admin
    app_.add_handler(CommandHandler("users", users_cmd))
    app_.add_handler(CommandHandler("grant", grant_cmd))
    app_.add_handler(CommandHandler("block", block_cmd))
    app_.add_handler(CommandHandler("unblock", unblock_cmd))
    app_.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app_.add_handler(CommandHandler(["feedstatus","feedstats"], feedstatus_cmd))

    # buttons + text relay
    app_.add_handler(CallbackQueryHandler(button_router))
    app_.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, capture_text_messages))

    log.info("Handlers & jobs registered.")
    return app_

# ---------- Local polling (optional) ----------
if __name__ == "__main__":
    import asyncio
    async def _main():
        app = build_application()
        log.info("Starting bot in polling mode (local debug)...")
        await app.initialize(); await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        try: await asyncio.Event().wait()
        finally:
            await app.updater.stop(); await app.stop(); await app.shutdown()
    asyncio.run(_main())
