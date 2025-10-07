# bot.py
# -*- coding: utf-8 -*-
"""
Telegram bot (python-telegram-bot v20+), English UI

- Welcome card + big inline buttons (functional)
- Shows Trial Start / Trial Ends / License Until + "Expires (in N days)"
- /whoami shows role (Admin/User) and omits username line if empty
- Keywords persistence: /addkeyword, /keywords, /delkeyword
- Admin controls:
    /users, /grant <telegram_id> <days>, /block, /unblock, /broadcast <text>, /feedstatus (/feedstats)
- User → Admin extension flow: /extend [message] → admin receives Approve buttons (+3/+7/+14/+30 days) & Decline
- Automatic reminder 24h before expiration (trial or license) via JobQueue
- UI/help avoids the word "affiliate" (functionality unchanged)
"""

import os
import logging
from math import ceil
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from telegram.constants import ParseMode

# ---------- DB imports (defensive) ----------
SessionLocal = None
User = None
Keyword = None
JobSent = None

try:
    from db import SessionLocal as _SessionLocal, User as _User, Keyword as _Keyword, JobSent as _JobSent
    SessionLocal = _SessionLocal
    User = _User
    Keyword = _Keyword
    JobSent = _JobSent
except Exception:
    pass

log = logging.getLogger("bot")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

UTC = timezone.utc

# ---------- ENV ----------
DEFAULT_TRIAL_DAYS = int(os.getenv("DEFAULT_TRIAL_DAYS", "10"))
ADMIN_CONTACT_TEXT = os.getenv("ADMIN_CONTACT_TEXT", "Contact the admin via this chat.")
# day options for inline approvals
APPROVE_DAY_OPTIONS = [3, 7, 14, 30]

# ---------- Helpers ----------

def now_utc() -> datetime:
    return datetime.now(UTC)

def is_admin_id(tg_id: int) -> bool:
    admin_id = (os.getenv("ADMIN_ID") or "").strip()
    if not admin_id:
        return False
    try:
        return str(tg_id) == str(int(admin_id))
    except Exception:
        return str(tg_id) == admin_id

def is_admin(update: Update) -> bool:
    return is_admin_id(update.effective_user.id)

def db_available() -> bool:
    return SessionLocal is not None and User is not None and Keyword is not None

def _get_user_id_field() -> str:
    for cand in ("telegram_id", "tg_id", "chat_id", "user_id"):
        if hasattr(User, cand):
            return cand
    raise RuntimeError("User model must expose telegram id (telegram_id/tg_id/chat_id/user_id).")

def _get_keyword_text_field() -> str:
    for fld in ("text", "name", "word", "value", "keyword"):
        if hasattr(Keyword, fld):
            return fld
    raise RuntimeError("Keyword model must have text/name/word/value/keyword field.")

def _user_lookup(db, tg_id: int):
    uf = _get_user_id_field()
    col = getattr(User, uf)
    try:
        is_str = col.property.columns[0].type.python_type is str  # type: ignore
    except Exception:
        is_str = False
    return db.query(User).filter(col == (str(tg_id) if is_str else tg_id)).first()

def _get_or_create_user(db, tg_id: int):
    u = _user_lookup(db, tg_id)
    if u:
        return u
    uf = _get_user_id_field()
    u = User()
    try:
        setattr(u, uf, tg_id)
    except Exception:
        setattr(u, uf, str(tg_id))
    # initialize flags/dates if exist
    if hasattr(u, "trial_start") and getattr(u, "trial_start") in (None, ""):
        setattr(u, "trial_start", now_utc())
    if hasattr(u, "trial_ends") and getattr(u, "trial_ends") in (None, ""):
        setattr(u, "trial_ends", now_utc() + timedelta(days=DEFAULT_TRIAL_DAYS))
    if hasattr(u, "active") and getattr(u, "active") is None:
        setattr(u, "active", True)
    if hasattr(u, "blocked") and getattr(u, "blocked") is None:
        setattr(u, "blocked", False)
    if hasattr(u, "created_at") and getattr(u, "created_at") is None:
        setattr(u, "created_at", now_utc())
    db.add(u); db.commit(); db.refresh(u)
    return u

def _list_keywords(db, user) -> List[Keyword]:
    if hasattr(user, "keywords") and getattr(user, "keywords") is not None:
        try:
            return list(getattr(user, "keywords"))
        except Exception:
            pass
    q = None
    for uf in ("id", "user_id", "pk"):
        if hasattr(user, uf):
            uid = getattr(user, uf)
            for kf in ("user_id", "uid", "owner_id"):
                if hasattr(Keyword, kf):
                    q = db.query(Keyword).filter(getattr(Keyword, kf) == uid)
                    break
        if q is not None:
            break
    return list(q.all()) if q is not None else []

def _kw_id(k):
    for fld in ("id", "pk"):
        if hasattr(k, fld):
            return getattr(k, fld)
    return None

def _kw_text(k) -> str:
    tf = _get_keyword_text_field()
    return str(getattr(k, tf) or "")

def _user_dates(u) -> Tuple[Optional[datetime], Optional[datetime], Optional[datetime]]:
    return getattr(u, "trial_start", None), getattr(u, "trial_ends", None), getattr(u, "license_until", None)

def _fmt(dt: Optional[datetime]) -> str:
    if not dt:
        return "None"
    try:
        return dt.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%SZ")
    except Exception:
        return str(dt)

def _days_remaining(exp: Optional[datetime]) -> str:
    if not exp:
        return "—"
    try:
        delta = exp.astimezone(UTC) - now_utc()
    except Exception:
        delta = exp - now_utc()
    secs = delta.total_seconds()
    if secs < 0:
        return f"expired {ceil(abs(secs)/86400)} day(s) ago"
    return f"in {ceil(secs/86400)} day(s)"

def _active_blocked(u) -> Tuple[str, str]:
    active = "✅"
    if hasattr(u, "active"):
        try:
            active = "✅" if bool(getattr(u, "active")) else "❌"
        except Exception:
            pass
    blocked = "❌"
    if hasattr(u, "blocked"):
        try:
            blocked = "✅" if bool(getattr(u, "blocked")) else "❌"
        except Exception:
            blocked = "❌"
    return active, blocked

def _effective_expiry(u) -> Optional[datetime]:
    lic = getattr(u, "license_until", None)
    return lic if lic else getattr(u, "trial_ends", None)

def _extend_days(dt0: Optional[datetime], days: int) -> datetime:
    base = dt0 if dt0 and dt0 > now_utc() else now_utc()
    return base + timedelta(days=days)

# ---------- UI ----------

def main_menu_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("➕ Add Keywords", callback_data="act:add"),
         InlineKeyboardButton("⚙️ Settings", callback_data="act:settings")],
        [InlineKeyboardButton("🆘 Help", callback_data="act:help"),
         InlineKeyboardButton("💾 Saved", callback_data="act:saved")],
        [InlineKeyboardButton("📞 Contact", callback_data="act:contact"),
         InlineKeyboardButton("👑 Admin", callback_data="act:admin")],
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
    "2️⃣ Set your countries with <code>/setcountry US,UK</code> (or <code>ALL</code>). \n"
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
    ts, te, lu = _user_dates(u)
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
        await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

# ---------- Commands (user) ----------

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME_HEAD, reply_markup=main_menu_keyboard(),
                                    parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    if db_available():
        db = SessionLocal()
        try:
            u = _get_or_create_user(db, update.effective_user.id)
            kws = [_kw_text(k) for k in _list_keywords(db, u)]
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
    if uname:
        text += f"\n@{uname}"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def addkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: <code>/addkeyword &lt;word&gt;</code>", parse_mode=ParseMode.HTML)
        return
    word = " ".join(context.args).strip()
    if not db_available():
        await update.message.reply_text(f"(demo) ✅ Added keyword: <code>{word}</code> (no DB)", parse_mode=ParseMode.HTML)
        return
    db = SessionLocal()
    try:
        u = _get_or_create_user(db, update.effective_user.id)
        k = Keyword()
        setattr(k, _get_keyword_text_field(), word)
        # relationship/FK
        set_ok = False
        if hasattr(Keyword, "user"):
            try: setattr(k, "user", u); set_ok = True
            except Exception: pass
        if not set_ok:
            for uf in ("id", "user_id", "pk"):
                if hasattr(u, uf):
                    uid = getattr(u, uf)
                    for kf in ("user_id", "uid", "owner_id"):
                        if hasattr(Keyword, kf):
                            setattr(k, kf, uid); set_ok = True; break
                if set_ok: break
        db.add(k); db.commit(); db.refresh(k)
        await update.message.reply_text(f"✅ Added keyword: <code>{word}</code>", parse_mode=ParseMode.HTML)
    except Exception as e:
        log.exception("addkeyword failed: %s", e)
        await update.message.reply_text("⚠️ Error while saving your keyword.")
    finally:
        db.close()

async def keywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not db_available():
        await update.message.reply_text("(demo) DB is not available here.")
        return
    db = SessionLocal()
    try:
        u = _get_or_create_user(db, update.effective_user.id)
        kws = _list_keywords(db, u)
        shown = []
        if kws:
            lines = ["📃 <b>Your keywords</b>"]
            for k in kws:
                shown.append(_kw_text(k))
                lines.append(f"• <code>{_kw_id(k)}</code> — {_kw_text(k)}")
            await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text("You have no keywords yet. Add one with <code>/addkeyword ...</code>",
                                            parse_mode=ParseMode.HTML)
        await update.message.reply_text(settings_card_text(u, shown), parse_mode=ParseMode.HTML,
                                        disable_web_page_preview=True)
    except Exception as e:
        log.exception("keywords_cmd failed: %s", e)
        await update.message.reply_text("⚠️ Error while reading your keywords.")
    finally:
        db.close()

async def delkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: <code>/delkeyword &lt;word&gt;</code> or <code>/delkeyword &lt;id&gt;</code>",
                                        parse_mode=ParseMode.HTML)
        return
    ident = " ".join(context.args).strip()
    if not db_available():
        await update.message.reply_text(f"(demo) ✅ Deleted: <code>{ident}</code> (no DB)", parse_mode=ParseMode.HTML)
        return
    db = SessionLocal()
    try:
        u = _get_or_create_user(db, update.effective_user.id)
        deleted = 0
        # try id
        try:
            kid = int(ident)
            q = db.query(Keyword)
            for uf in ("id", "user_id", "pk"):
                if hasattr(u, uf):
                    uid = getattr(u, uf)
                    for kf in ("user_id", "uid", "owner_id"):
                        if hasattr(Keyword, kf):
                            q = q.filter(getattr(Keyword, kf) == uid); break
                    break
            if hasattr(Keyword, "id"): q = q.filter(Keyword.id == kid)
            elif hasattr(Keyword, "pk"): q = q.filter(Keyword.pk == kid)
            for row in q.all(): db.delete(row); deleted += 1
            db.commit()
        except Exception:
            q = db.query(Keyword)
            for uf in ("id", "user_id", "pk"):
                if hasattr(u, uf):
                    uid = getattr(u, uf)
                    for kf in ("user_id", "uid", "owner_id"):
                        if hasattr(Keyword, kf):
                            q = q.filter(getattr(Keyword, kf) == uid); break
                    break
            tf = _get_keyword_text_field()
            for row in q.filter(getattr(Keyword, tf) == ident).all():
                db.delete(row); deleted += 1
            db.commit()
        if deleted:
            await update.message.reply_text(f"🗑️ Deleted {deleted} keyword(s) for <code>{ident}</code>", parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text("Nothing found to delete.")
    except Exception as e:
        log.exception("delkeyword_cmd failed: %s", e)
        await update.message.reply_text("⚠️ Error while deleting keyword.")
    finally:
        db.close()

# ---------- User → Admin extension flow ----------

def _approval_keyboard(user_id: int) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(f"✅ +{d} days", callback_data=f"adm:approve:{user_id}:{d}")]
            for d in APPROVE_DAY_OPTIONS]
    rows.append([InlineKeyboardButton("❌ Decline", callback_data=f"adm:decline:{user_id}")])
    return InlineKeyboardMarkup(rows)

async def extend_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_msg = " ".join(context.args).strip() if context.args else ""
    admin_id_env = os.getenv("ADMIN_ID")
    if not admin_id_env:
        await update.message.reply_text("Admin is not configured.")
        return
    text = f"🔔 Extension request from <code>{user_id}</code>"
    if user_msg:
        text += f"\n\n📝 <b>Message</b>:\n{user_msg}"
    await context.bot.send_message(chat_id=int(admin_id_env), text=text,
                                   parse_mode=ParseMode.HTML, reply_markup=_approval_keyboard(user_id))
    await update.message.reply_text("Your request was sent to the admin. You'll receive a reply soon.")

# ---------- Admin actions ----------

def _list_all_users(db) -> List[User]:
    try:
        return list(db.query(User).all())
    except Exception:
        return []

def _disp_id(u) -> str:
    for f in ("telegram_id", "tg_id", "chat_id", "user_id", "id", "pk"):
        if hasattr(u, f):
            return str(getattr(u, f))
    return "?"

async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("Admin only.")
        return
    if not db_available():
        await update.message.reply_text("DB not available.")
        return
    db = SessionLocal()
    try:
        users = _list_all_users(db)
        lines = ["👥 <b>Users</b>"]
        for u in users[:200]:
            kws = _list_keywords(db, u)
            ts, te, lu = _user_dates(u)
            active, blocked = _active_blocked(u)
            lines.append(
                f"• <code>{_disp_id(u)}</code> — kw:{len(kws)} | "
                f"trial:{_fmt(ts)}→{_fmt(te)} | lic:{_fmt(lu)} | A:{active} B:{blocked}"
            )
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    finally:
        db.close()

async def grant_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("Admin only.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: <code>/grant &lt;telegram_id&gt; &lt;days&gt;</code>", parse_mode=ParseMode.HTML); return
    if not db_available(): await update.message.reply_text("DB not available."); return
    try:
        target_id = int(context.args[0]); days = int(context.args[1])
    except Exception:
        await update.message.reply_text("Usage: <code>/grant &lt;telegram_id&gt; &lt;days&gt;</code>", parse_mode=ParseMode.HTML); return
    db = SessionLocal()
    try:
        u = _user_lookup(db, target_id)
        if not u: await update.message.reply_text("User not found."); return
        lic = getattr(u, "license_until", None)
        if hasattr(u, "license_until"): setattr(u, "license_until", _extend_days(lic, days))
        elif hasattr(u, "trial_ends"): setattr(u, "trial_ends", _extend_days(getattr(u, "trial_ends", None), days))
        if hasattr(u, "active"): setattr(u, "active", True)
        if hasattr(u, "blocked"): setattr(u, "blocked", False)
        db.commit()
        ts, te, lu = _user_dates(u)
        await update.message.reply_text(
            "✅ Granted access.\n"
            f"user: <code>{_disp_id(u)}</code>\n"
            f"trial: {_fmt(ts)} → {_fmt(te)}\n"
            f"license_until: {_fmt(lu)}", parse_mode=ParseMode.HTML
        )
        try:
            await context.bot.send_message(chat_id=target_id, text=f"✅ Your access was extended by {days} day(s).")
        except Exception: pass
    finally:
        db.close()

async def block_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): 
        await update.message.reply_text("Admin only."); return
    if not context.args:
        await update.message.reply_text("Usage: <code>/block &lt;telegram_id&gt;</code>", parse_mode=ParseMode.HTML); return
    if not db_available(): await update.message.reply_text("DB not available."); return
    try: target_id = int(context.args[0])
    except Exception:
        await update.message.reply_text("Usage: <code>/block &lt;telegram_id&gt;</code>", parse_mode=ParseMode.HTML); return
    db = SessionLocal()
    try:
        u = _user_lookup(db, target_id)
        if not u: await update.message.reply_text("User not found."); return
        if hasattr(u, "blocked"): setattr(u, "blocked", True)
        if hasattr(u, "active"): setattr(u, "active", False)
        db.commit()
        await update.message.reply_text("✅ User blocked.")
    finally:
        db.close()

async def unblock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): 
        await update.message.reply_text("Admin only."); return
    if not context.args:
        await update.message.reply_text("Usage: <code>/unblock &lt;telegram_id&gt;</code>", parse_mode=ParseMode.HTML); return
    if not db_available(): await update.message.reply_text("DB not available."); return
    try: target_id = int(context.args[0])
    except Exception:
        await update.message.reply_text("Usage: <code>/unblock &lt;telegram_id&gt;</code>", parse_mode=ParseMode.HTML); return
    db = SessionLocal()
    try:
        u = _user_lookup(db, target_id)
        if not u: await update.message.reply_text("User not found."); return
        if hasattr(u, "blocked"): setattr(u, "blocked", False)
        if hasattr(u, "active"): setattr(u, "active", True)
        db.commit()
        await update.message.reply_text("✅ User unblocked.")
    finally:
        db.close()

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): 
        await update.message.reply_text("Admin only."); return
    msg = " ".join(context.args).strip()
    if not msg:
        await update.message.reply_text("Usage: <code>/broadcast &lt;text&gt;</code>", parse_mode=ParseMode.HTML); return
    if not db_available(): await update.message.reply_text("DB not available."); return

    from httpx import AsyncClient
    token = (os.getenv("BOT_TOKEN") or "").strip()
    api = f"https://api.telegram.org/bot{token}/sendMessage"

    db = SessionLocal()
    sent = 0
    try:
        users = _list_all_users(db)
        async with AsyncClient(timeout=float(os.getenv("HTTP_TIMEOUT", "20"))) as client:
            for u in users:
                if hasattr(u, "blocked") and bool(getattr(u, "blocked")): continue
                if hasattr(u, "active") and not bool(getattr(u, "active")): continue
                chat_id = None
                for f in ("chat_id", "telegram_id", "tg_id", "user_id", "id"):
                    if hasattr(u, f):
                        chat_id = getattr(u, f); break
                if not chat_id: continue
                try:
                    await client.post(api, json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML",
                                                 "disable_web_page_preview": True})
                    sent += 1
                except Exception: pass
        await update.message.reply_text(f"📣 Broadcast sent to {sent} users.")
    finally:
        db.close()

async def feedstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show sent jobs per platform for the last 24h. Works even without DB (falls back to zeros)."""
    if not is_admin(update):
        await update.message.reply_text("Admin only.")
        return

    # Known platforms (labels)
    known = [
        "Freelancer", "PeoplePerHour", "Malt", "Workana", "Guru", "99designs", "Toptal",
        "Codeable", "YunoJuno", "Worksome", "twago", "freelancermap", "Wripple",
        "JobFind", "Skywalker", "Kariera", "Careerjet"
    ]
    counters: Dict[str, int] = {k: 0 for k in known}

    # Map prefix->label (as stored in job_id like "freelancer-12345")
    prefix_map = {
        "freelancer": "Freelancer",
        "pph": "PeoplePerHour",
        "malt": "Malt",
        "workana": "Workana",
        "guru": "Guru",
        "99designs": "99designs",
        "toptal": "Toptal",
        "codeable": "Codeable",
        "yuno_juno": "YunoJuno",
        "worksome": "Worksome",
        "twago": "twago",
        "freelancermap": "freelancermap",
        "wripple": "Wripple",
        "jobfind": "JobFind",
        "sky": "Skywalker",
        "kariera": "Kariera",
        "careerjet": "Careerjet",
    }

    # Try DB
    used_db = False
    if SessionLocal is not None and JobSent is not None:
        db = SessionLocal()
        try:
            since = now_utc() - timedelta(hours=24)
            rows = db.query(JobSent).filter(JobSent.created_at >= since).all()
            for r in rows:
                jid = (getattr(r, "job_id", "") or "").strip()
                pref = jid.split("-", 1)[0] if "-" in jid else ""
                label = prefix_map.get(pref)
                if label:
                    counters[label] = counters.get(label, 0) + 1
            used_db = True
        except Exception as e:
            log.warning("feedstatus query failed: %s", e)
        finally:
            try: db.close()
            except Exception: pass

    # Build message
    title = "📊 <b>Sent jobs by platform (last 24h)</b>"
    if not used_db:
        title += "\n<i>(DB not available — showing zeros)</i>"

    lines = [title]
    for src, n in sorted(counters.items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"• {src}: {n}")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

# ---------- Callback buttons ----------

async def button_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q: return
    data = q.data or ""
    await q.answer()
    if data == "act:add":
        await q.message.reply_text("Add a keyword with: <code>/addkeyword lighting</code>", parse_mode=ParseMode.HTML)
    elif data == "act:settings":
        if not db_available():
            await q.message.reply_text("(demo) DB not available."); return
        db = SessionLocal()
        try:
            u = _get_or_create_user(db, q.from_user.id)
            kws = [_kw_text(k) for k in _list_keywords(db, u)]
            await q.message.reply_text(settings_card_text(u, kws), parse_mode=ParseMode.HTML,
                                       disable_web_page_preview=True)
        finally:
            db.close()
    elif data == "act:help":
        await _send_html(update, context, HELP_TEXT)
    elif data == "act:saved":
        await q.message.reply_text("Saved items will appear here (coming soon).")
    elif data == "act:contact":
        await q.message.reply_text(ADMIN_CONTACT_TEXT + "\nYou can also use /extend to ask for more days.")
    elif data == "act:admin":
        if not is_admin_id(q.from_user.id):
            await q.message.reply_text("Admin only.")
        else:
            await _send_html(update, context,
                "Admin commands:\n"
                "<code>/users</code>\n"
                "<code>/grant &lt;telegram_id&gt; &lt;days&gt;</code>\n"
                "<code>/block &lt;telegram_id&gt;</code> / <code>/unblock &lt;telegram_id&gt;</code>\n"
                "<code>/broadcast &lt;text&gt;</code>\n"
                "<code>/feedstatus</code>"
            )
    elif data.startswith("adm:approve:") and is_admin_id(q.from_user.id):
        # adm:approve:<user_id>:<days>
        parts = data.split(":")
        if len(parts) == 4:
            target = int(parts[2]); days = int(parts[3])
            if not db_available():
                await q.message.reply_text("DB not available."); return
            db = SessionLocal()
            try:
                u = _user_lookup(db, target)
                if not u:
                    await q.message.reply_text("User not found."); return
                if hasattr(u, "license_until"):
                    setattr(u, "license_until", _extend_days(getattr(u, "license_until", None), days))
                elif hasattr(u, "trial_ends"):
                    setattr(u, "trial_ends", _extend_days(getattr(u, "trial_ends", None), days))
                if hasattr(u, "active"): setattr(u, "active", True)
                if hasattr(u, "blocked"): setattr(u, "blocked", False)
                db.commit()
                await q.message.reply_text(f"✅ Approved. Extended {days} day(s) for {target}.")
                try:
                    await context.bot.send_message(chat_id=target,
                        text=f"✅ Approved. Your access was extended by {days} day(s).")
                except Exception: pass
            finally:
                db.close()
    elif data.startswith("adm:decline:") and is_admin_id(q.from_user.id):
        target = int(data.split(":")[-1])
        await q.message.reply_text(f"❌ Declined extension for {target}.")
        try:
            await context.bot.send_message(chat_id=target, text="❌ Your extension request was declined.")
        except Exception:
            pass

# ---------- Reminder job ----------

async def check_expirations(context: ContextTypes.DEFAULT_TYPE):
    """Runs daily. Sends reminder to users expiring within 24h (license or trial)."""
    if not db_available():
        return
    admin_id_env = os.getenv("ADMIN_ID")
    db = SessionLocal()
    now = now_utc()
    in_24h = now + timedelta(hours=24)
    try:
        users = _list_all_users(db)
        for u in users:
            if hasattr(u, "blocked") and bool(getattr(u, "blocked")):
                continue
            exp = _effective_expiry(u)
            if not exp:
                continue
            try:
                exp_utc = exp.astimezone(UTC)
            except Exception:
                exp_utc = exp
            if now <= exp_utc <= in_24h:
                # remind user
                chat_id = None
                for f in ("chat_id", "telegram_id", "tg_id", "user_id", "id"):
                    if hasattr(u, f):
                        chat_id = getattr(u, f); break
                if chat_id:
                    try:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=f"⏳ Reminder: your access expires on <b>{_fmt(exp_utc)}</b> "
                                 f"({_days_remaining(exp_utc)}). Use /extend to request extra days.",
                            parse_mode=ParseMode.HTML
                        )
                    except Exception:
                        pass
                # notify admin
                if admin_id_env:
                    try:
                        await context.bot.send_message(
                            chat_id=int(admin_id_env),
                            text=f"⏳ User <code>{_disp_id(u)}</code> expires on <b>{_fmt(exp_utc)}</b> "
                                 f"({_days_remaining(exp_utc)}).",
                            parse_mode=ParseMode.HTML
                        )
                    except Exception:
                        pass
    finally:
        db.close()

# ---------- Application Builder ----------

async def _post_init(app: Application):
    try:
        app.job_queue.run_repeating(check_expirations, interval=24 * 3600, first=60)
        log.info("Expiration reminder scheduled.")
    except Exception as e:
        log.warning("Could not schedule reminder: %s", e)

def build_application() -> Application:
    token = (os.getenv("BOT_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is not set in environment variables.")
    app_ = ApplicationBuilder().token(token).post_init(_post_init).build()

    # user commands
    app_.add_handler(CommandHandler("start", start_cmd))
    app_.add_handler(CommandHandler("help", help_cmd))
    app_.add_handler(CommandHandler("whoami", whoami_cmd))
    app_.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app_.add_handler(CommandHandler("keywords", keywords_cmd))
    app_.add_handler(CommandHandler("delkeyword", delkeyword_cmd))
    app_.add_handler(CommandHandler("extend", extend_cmd))

    # admin commands
    app_.add_handler(CommandHandler("users", users_cmd))
    app_.add_handler(CommandHandler("grant", grant_cmd))
    app_.add_handler(CommandHandler("block", block_cmd))
    app_.add_handler(CommandHandler("unblock", unblock_cmd))
    app_.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app_.add_handler(CommandHandler(["feedstatus", "feedstats"], feedstatus_cmd))

    # buttons
    app_.add_handler(CallbackQueryHandler(button_router))

    log.info("Handlers & jobs registered.")
    return app_


# ---------- Local polling (optional) ----------

if __name__ == "__main__":
    import asyncio
    async def _main():
        app = build_application()
        log.info("Starting bot in polling mode (local debug)...")
        await app.initialize()
        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        try:
            await asyncio.Event().wait()
        finally:
            await app.updater.stop()
            await app.stop()
            await app.shutdown()
    asyncio.run(_main())
