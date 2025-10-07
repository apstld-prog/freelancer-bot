# bot.py
# -*- coding: utf-8 -*-
"""
Telegram bot (python-telegram-bot v20+), English UI.

Keeps the original layout (welcome card + big buttons) and adds:
- Trial/License fields in the main screen (Start & Ends)
- Admin commands:
  /users
  /grant <telegram_id> <days>
  /block <telegram_id>
  /unblock <telegram_id>
  /broadcast <text>
  /feedstatus (alias /feedstats)
- Keywords persistence: /addkeyword, /keywords, /delkeyword

The code is defensive against differing DB schemas. It tries fields:
- user id: telegram_id / tg_id / chat_id / user_id
- status: active / blocked
- dates: trial_start, trial_ends, license_until, created_at
"""

import os
import logging
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
    ContextTypes,
)

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


# ---------- Helpers ----------

UTC = timezone.utc

def now_utc() -> datetime:
    return datetime.now(UTC)

def is_admin(update: Update) -> bool:
    admin_id = (os.getenv("ADMIN_ID") or "").strip()
    if not admin_id:
        return False
    try:
        return str(update.effective_user.id) == str(int(admin_id))
    except Exception:
        return str(update.effective_user.id) == admin_id

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
    # initialize dates if fields exist
    if hasattr(u, "trial_start") and getattr(u, "trial_start") in (None, ""):
        setattr(u, "trial_start", now_utc())
    if hasattr(u, "trial_ends") and getattr(u, "trial_ends") in (None, ""):
        # default 10-day trial
        setattr(u, "trial_ends", now_utc() + timedelta(days=10))
    if hasattr(u, "active") and getattr(u, "active") is None:
        setattr(u, "active", True)
    if hasattr(u, "blocked") and getattr(u, "blocked") is None:
        setattr(u, "blocked", False)
    if hasattr(u, "created_at") and getattr(u, "created_at") is None:
        setattr(u, "created_at", now_utc())
    db.add(u)
    db.commit()
    db.refresh(u)
    return u

def _add_keyword(db, user, word: str):
    word = (word or "").strip()
    if not word:
        return None
    kw = Keyword()
    # set keyword text
    setattr(kw, _get_keyword_text_field(), word)
    # owner relation
    set_ok = False
    if hasattr(Keyword, "user"):
        try:
            setattr(kw, "user", user); set_ok = True
        except Exception:
            pass
    if not set_ok:
        # fallback FK
        for uf in ("id", "user_id", "pk"):
            if hasattr(user, uf):
                uid = getattr(user, uf)
                for kf in ("user_id", "uid", "owner_id"):
                    if hasattr(Keyword, kf):
                        setattr(kw, kf, uid); set_ok = True; break
            if set_ok: break
    if hasattr(kw, "created_at") and getattr(kw, "created_at") is None:
        setattr(kw, "created_at", now_utc())
    db.add(kw)
    db.commit()
    db.refresh(kw)
    return kw

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
    return str(getattr(k, _get_keyword_text_field()) or "")

def _get_user_dates(u) -> Tuple[Optional[datetime], Optional[datetime], Optional[datetime]]:
    """Return (trial_start, trial_ends, license_until) if attributes exist."""
    ts = getattr(u, "trial_start", None)
    te = getattr(u, "trial_ends", None)
    lu = getattr(u, "license_until", None)
    return ts, te, lu

def _fmt_dt(dt: Optional[datetime]) -> str:
    if not dt:
        return "None"
    try:
        return dt.astimezone(UTC).isoformat()
    except Exception:
        return str(dt)

def _status_flags(u) -> Tuple[str, str]:
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

# ---------- UI (matches screenshot) ----------

def main_menu_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("➕ Add Keywords", callback_data="noop"),
         InlineKeyboardButton("⚙️ Settings", callback_data="noop")],
        [InlineKeyboardButton("🆘 Help", callback_data="noop"),
         InlineKeyboardButton("💾 Saved", callback_data="noop")],
        [InlineKeyboardButton("📞 Contact", callback_data="noop"),
         InlineKeyboardButton("👑 Admin", callback_data="noop")],
    ]
    return InlineKeyboardMarkup(rows)

WELCOME_HEAD = (
    "👋 <b>Welcome to Freelancer Alert Bot!</b>\n\n"
    "🎁 <b>You have a 10-day free trial.</b>\n"
    "Automatically finds matching freelance jobs from top\n"
    "platforms and sends you instant alerts with affiliate-safe links.\n\n"
    "Use <code>/help</code> to see how it works."
)

FEATURES_TEXT = (
    "✨ <b>Features</b>\n"
    "• Realtime job alerts (Freelancer API)\n"
    "• Affiliate-wrapped <b>Proposal</b> & <b>Original</b> links\n"
    "• Budget shown + USD conversion\n"
    "• ⭐ Keep / 🗑️ Delete buttons\n"
    "• 10-day free trial, extend via admin\n"
    "• Multi-keyword search (single/all modes)\n"
    "• Platforms by country (incl. GR boards)"
)

def settings_card_text(u, kws: List[str]) -> str:
    ts, te, lu = _get_user_dates(u)
    active, blocked = _status_flags(u)
    kw_display = ", ".join(kws) if kws else "—"
    return (
        "🛠️ <b>Your Settings</b>\n"
        f"• Keywords: {kw_display}\n"
        "• Countries: ALL\n"
        "• Proposal template: (none)\n\n"
        f"🟢 Trial start: {_fmt_dt(ts)}\n"
        f"⏳ Trial ends: {_fmt_dt(te)}\n"
        f"🔑 License until: {_fmt_dt(lu)}\n"
        f"🟢 Active: {active}\n"
        f"⛔ Blocked: {blocked}\n\n"
        "📜 Platforms monitored:\n"
        "<a href='https://www.freelancer.com/'>Freelancer.com</a> (affiliate links), "
        "PeoplePerHour, Malt, Workana, Guru, 99designs, Toptal*, Codeable*, YunoJuno*, Worksome*, "
        "twago, freelancermap\n"
        "(* referral/curated platforms)\n\n"
        "Greece: JobFind.gr, Skywalker.gr, Kariera.gr\n\n"
        "For extension, contact the admin."
    )

# ---------- Commands (user) ----------

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Welcome block
    await update.message.reply_text(WELCOME_HEAD, reply_markup=main_menu_keyboard(), disable_web_page_preview=True)

    # Show settings card with dates (trial start/ends) in the main menu
    if db_available():
        db = SessionLocal()
        try:
            u = _get_or_create_user(db, update.effective_user.id)
            kws = [_kw_text(k) for k in _list_keywords(db, u)]
            await update.message.reply_text(settings_card_text(u, kws), parse_mode="HTML", disable_web_page_preview=True)
        finally:
            db.close()

    # Features block
    await update.message.reply_text(FEATURES_TEXT, disable_web_page_preview=True)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🧭 <b>Help / How it works</b>\n\n"
        "1) Add keywords with <code>/addkeyword python</code>\n"
        "2) List your keywords with <code>/keywords</code>\n"
        "3) Delete with <code>/delkeyword &lt;word|id&gt;</code>\n"
        "4) Stats (admin): <code>/feedstatus</code>\n\n"
        "When your free trial ends, please contact the admin to extend your access.\n\n"
        "Platforms monitored:\n"
        "Global: Freelancer, PeoplePerHour, Malt, Workana, twago, freelancermap, YunoJuno*, Worksome*, "
        "Codeable*, Guru, 99designs, Wripple, Toptal\n"
        "Greece: JobFind, Skywalker, Kariera, Careerjet\n\n"
        "<i>Duplicates are deduped with affiliate-first preference.</i>"
    )
    await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)

async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    uname = update.effective_user.username or "—"
    await update.message.reply_text(f"🆔 Your ID: <code>{uid}</code>\n@{uname}", parse_mode="HTML")

async def addkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: <code>/addkeyword &lt;word&gt;</code>", parse_mode="HTML")
        return
    word = " ".join(context.args).strip()
    if not db_available():
        await update.message.reply_text(f"(demo) ✅ Added keyword: <code>{word}</code> (no DB)", parse_mode="HTML")
        return
    db = SessionLocal()
    try:
        u = _get_or_create_user(db, update.effective_user.id)
        k = _add_keyword(db, u, word)
        if not k:
            await update.message.reply_text("Could not save your keyword.")
            return
        await update.message.reply_text(f"✅ Added keyword: <code>{word}</code>", parse_mode="HTML")
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
        if not kws:
            await update.message.reply_text("You have no keywords yet. Add one with <code>/addkeyword ...</code>", parse_mode="HTML")
            return
        lines = ["📃 <b>Your keywords</b>"]
        shown = []
        for k in kws:
            shown.append(_kw_text(k))
            lines.append(f"• <code>{_kw_id(k)}</code> — {_kw_text(k)}")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
        # brief settings card
        await update.message.reply_text(settings_card_text(u, shown), parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        log.exception("keywords_cmd failed: %s", e)
        await update.message.reply_text("⚠️ Error while reading your keywords.")
    finally:
        db.close()

async def delkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: <code>/delkeyword &lt;word&gt;</code> or <code>/delkeyword &lt;id&gt;</code>", parse_mode="HTML")
        return
    ident = " ".join(context.args).strip()
    if not db_available():
        await update.message.reply_text(f"(demo) ✅ Deleted: <code>{ident}</code> (no DB)", parse_mode="HTML")
        return
    db = SessionLocal()
    try:
        u = _get_or_create_user(db, update.effective_user.id)
        deleted = 0
        # By numeric id
        try:
            kid = int(ident)
            q = db.query(Keyword)
            for uf in ("id", "user_id", "pk"):
                if hasattr(u, uf):
                    uid = getattr(u, uf)
                    for kf in ("user_id", "uid", "owner_id"):
                        if hasattr(Keyword, kf):
                            q = q.filter(getattr(Keyword, kf) == uid)
                            break
                    break
            if hasattr(Keyword, "id"):
                q = q.filter(Keyword.id == kid)
            elif hasattr(Keyword, "pk"):
                q = q.filter(Keyword.pk == kid)
            for row in q.all():
                db.delete(row); deleted += 1
            db.commit()
        except Exception:
            # By exact text
            q = db.query(Keyword)
            for uf in ("id", "user_id", "pk"):
                if hasattr(u, uf):
                    uid = getattr(u, uf)
                    for kf in ("user_id", "uid", "owner_id"):
                        if hasattr(Keyword, kf):
                            q = q.filter(getattr(Keyword, kf) == uid)
                            break
                    break
            tf = _get_keyword_text_field()
            rows = q.filter(getattr(Keyword, tf) == ident).all()
            for r in rows:
                db.delete(r); deleted += 1
            db.commit()

        if deleted:
            await update.message.reply_text(f"🗑️ Deleted {deleted} keyword(s) for <code>{ident}</code>", parse_mode="HTML")
        else:
            await update.message.reply_text("Nothing found to delete.")
    except Exception as e:
        log.exception("delkeyword_cmd failed: %s", e)
        await update.message.reply_text("⚠️ Error while deleting keyword.")
    finally:
        db.close()


# ---------- Commands (admin) ----------

def _list_all_users(db) -> List[User]:
    try:
        return list(db.query(User).all())
    except Exception:
        return []

def _get_user_display_id(u) -> str:
    for f in ("telegram_id", "tg_id", "chat_id", "user_id", "id", "pk"):
        if hasattr(u, f):
            val = getattr(u, f)
            return str(val)
    return "?"

async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if not db_available():
        await update.message.reply_text("DB not available.")
        return
    db = SessionLocal()
    try:
        users = _list_all_users(db)
        lines = ["👥 <b>Users</b>"]
        for u in users[:100]:
            kws = _list_keywords(db, u)
            ts, te, lu = _get_user_dates(u)
            active, blocked = _status_flags(u)
            lines.append(
                f"• <code>{_get_user_display_id(u)}</code> — kw:{len(kws)} | "
                f"trial:{_fmt_dt(ts)}→{_fmt_dt(te)} | lic:{_fmt_dt(lu)} | A:{active} B:{blocked}"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)
    finally:
        db.close()

def _extend_days(dt0: Optional[datetime], days: int) -> datetime:
    base = dt0 if dt0 and dt0 > now_utc() else now_utc()
    return base + timedelta(days=days)

async def grant_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: <code>/grant &lt;telegram_id&gt; &lt;days&gt;</code>", parse_mode="HTML")
        return
    if not db_available():
        await update.message.reply_text("DB not available.")
        return
    try:
        target_id = int(context.args[0])
        days = int(context.args[1])
    except Exception:
        await update.message.reply_text("Usage: <code>/grant &lt;telegram_id&gt; &lt;days&gt;</code>", parse_mode="HTML")
        return

    db = SessionLocal()
    try:
        u = _user_lookup(db, target_id)
        if not u:
            await update.message.reply_text("User not found.")
            return

        # Prefer extending license_until; if not present, extend trial_ends.
        ts, te, lu = _get_user_dates(u)
        if hasattr(u, "license_until"):
            setattr(u, "license_until", _extend_days(lu, days))
        elif hasattr(u, "trial_ends"):
            setattr(u, "trial_ends", _extend_days(te, days))
        else:
            # if neither exists, create license_until
            try:
                setattr(u, "license_until", _extend_days(None, days))
            except Exception:
                pass

        if hasattr(u, "active"):
            try:
                setattr(u, "active", True)
            except Exception:
                pass
        if hasattr(u, "blocked"):
            try:
                setattr(u, "blocked", False)
            except Exception:
                pass

        db.commit()
        ts, te, lu = _get_user_dates(u)
        await update.message.reply_text(
            "✅ Granted access.\n"
            f"user: <code>{_get_user_display_id(u)}</code>\n"
            f"trial: {_fmt_dt(ts)} → {_fmt_dt(te)}\n"
            f"license_until: {_fmt_dt(lu)}",
            parse_mode="HTML"
        )
    except Exception as e:
        log.exception("grant failed: %s", e)
        await update.message.reply_text("⚠️ Grant failed.")
    finally:
        db.close()

async def block_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: <code>/block &lt;telegram_id&gt;</code>", parse_mode="HTML")
        return
    if not db_available():
        await update.message.reply_text("DB not available.")
        return
    try:
        target_id = int(context.args[0])
    except Exception:
        await update.message.reply_text("Usage: <code>/block &lt;telegram_id&gt;</code>", parse_mode="HTML")
        return
    db = SessionLocal()
    try:
        u = _user_lookup(db, target_id)
        if not u:
            await update.message.reply_text("User not found.")
            return
        if hasattr(u, "blocked"):
            setattr(u, "blocked", True)
        if hasattr(u, "active"):
            setattr(u, "active", False)
        db.commit()
        await update.message.reply_text("✅ User blocked.")
    finally:
        db.close()

async def unblock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: <code>/unblock &lt;telegram_id&gt;</code>", parse_mode="HTML")
        return
    if not db_available():
        await update.message.reply_text("DB not available.")
        return
    try:
        target_id = int(context.args[0])
    except Exception:
        await update.message.reply_text("Usage: <code>/unblock &lt;telegram_id&gt;</code>", parse_mode="HTML")
        return
    db = SessionLocal()
    try:
        u = _user_lookup(db, target_id)
        if not u:
            await update.message.reply_text("User not found.")
            return
        if hasattr(u, "blocked"):
            setattr(u, "blocked", False)
        if hasattr(u, "active"):
            setattr(u, "active", True)
        db.commit()
        await update.message.reply_text("✅ User unblocked.")
    finally:
        db.close()

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    msg = " ".join(context.args).strip()
    if not msg:
        await update.message.reply_text("Usage: <code>/broadcast &lt;text&gt;</code>", parse_mode="HTML")
        return
    if not db_available():
        await update.message.reply_text("DB not available.")
        return

    from httpx import AsyncClient
    token = (os.getenv("BOT_TOKEN") or "").strip()
    if not token:
        await update.message.reply_text("BOT_TOKEN missing.")
        return
    api = f"https://api.telegram.org/bot{token}/sendMessage"

    db = SessionLocal()
    sent = 0
    try:
        users = _list_all_users(db)
        async with AsyncClient(timeout=float(os.getenv("HTTP_TIMEOUT", "20"))) as client:
            for u in users:
                # skip blocked/inactive if fields exist
                if hasattr(u, "blocked") and bool(getattr(u, "blocked")):
                    continue
                if hasattr(u, "active") and not bool(getattr(u, "active")):
                    continue
                # chat id
                chat_id = None
                for f in ("chat_id", "telegram_id", "tg_id", "user_id", "id"):
                    if hasattr(u, f):
                        chat_id = getattr(u, f)
                        break
                if not chat_id:
                    continue
                try:
                    await client.post(api, json={
                        "chat_id": chat_id,
                        "text": msg,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True
                    })
                    sent += 1
                except Exception:
                    pass
        await update.message.reply_text(f"📣 Broadcast sent to {sent} users.")
    finally:
        db.close()

async def feedstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if SessionLocal is None or JobSent is None:
        await update.message.reply_text("DB not available in this environment.")
        return
    db = SessionLocal()
    try:
        since = now_utc() - timedelta(hours=24)
        rows = db.query(JobSent).filter(JobSent.created_at >= since).all()
        counts: Dict[str, int] = {}
        for r in rows:
            jid = (getattr(r, "job_id", "") or "").strip()
            pref = jid.split("-", 1)[0] if "-" in jid else "unknown"
            label = {
                "freelancer": "Freelancer",
                "pph": "PeoplePerHour",
                "kariera": "Kariera",
                "jobfind": "JobFind",
                "sky": "Skywalker",
                "careerjet": "Careerjet",
                "malt": "Malt",
                "workana": "Workana",
                "twago": "twago",
                "freelancermap": "freelancermap",
                "yuno_juno": "YunoJuno",
                "worksome": "Worksome",
                "codeable": "Codeable",
                "guru": "Guru",
                "99designs": "99designs",
                "wripple": "Wripple",
                "toptal": "Toptal",
            }.get(pref, pref or "unknown")
            counts[label] = counts.get(label, 0) + 1
        if not counts:
            await update.message.reply_text("📊 No sent jobs in the last 24h.")
            return
        lines = ["📊 <b>Sent jobs by platform (last 24h):</b>"]
        for src, n in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
            lines.append(f"• {src}: {n}")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
    finally:
        try:
            db.close()
        except Exception:
            pass


# ---------- Application Builder ----------

def build_application() -> Application:
    token = (os.getenv("BOT_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is not set in environment variables.")
    app_ = ApplicationBuilder().token(token).build()

    # user commands
    app_.add_handler(CommandHandler("start", start_cmd))
    app_.add_handler(CommandHandler("help", help_cmd))
    app_.add_handler(CommandHandler("whoami", whoami_cmd))
    app_.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app_.add_handler(CommandHandler("keywords", keywords_cmd))
    app_.add_handler(CommandHandler("delkeyword", delkeyword_cmd))

    # admin commands
    app_.add_handler(CommandHandler("users", users_cmd))
    app_.add_handler(CommandHandler("grant", grant_cmd))
    app_.add_handler(CommandHandler("block", block_cmd))
    app_.add_handler(CommandHandler("unblock", unblock_cmd))
    app_.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app_.add_handler(CommandHandler(["feedstatus", "feedstats"], feedstatus_cmd))

    log.info("Handlers: /start /help /whoami /addkeyword /keywords /delkeyword "
             "/users /grant /block /unblock /broadcast /feedstatus")
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
