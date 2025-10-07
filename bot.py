# bot.py
# -*- coding: utf-8 -*-
"""
Telegram bot (python-telegram-bot v20+)
- English-only texts
- /start, /help, /whoami
- Keywords persistence: /addkeyword, /keywords, /delkeyword
- Admin stats: /feedstatus (alias: /feedstats)
- build_application(): returns Application used by server.py
"""

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    Application,
    CommandHandler,
    ContextTypes,
)

# --- DB imports (SQLAlchemy models expected) ---
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
    # allow running without DB in dev; persistence commands will degrade gracefully
    pass

log = logging.getLogger(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

# ------------------------- Helpers -------------------------

def now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)

def is_admin(update: Update) -> bool:
    admin_id = (os.getenv("ADMIN_ID") or "").strip()
    if not admin_id:
        return False
    try:
        return str(update.effective_user.id) == str(int(admin_id))
    except Exception:
        return str(update.effective_user.id) == admin_id

def menu_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("➕ /addkeyword", callback_data="noop")],
        [InlineKeyboardButton("📃 /keywords", callback_data="noop")],
        [InlineKeyboardButton("🗑️ /delkeyword", callback_data="noop")],
        [InlineKeyboardButton("ℹ️ /help", callback_data="noop")],
    ]
    return InlineKeyboardMarkup(rows)

# ------------------------- DB utils (defensive) -------------------------

def db_available() -> bool:
    return SessionLocal is not None and User is not None and Keyword is not None

def _get_or_create_user(db, tg_id: int):
    # find the field holding telegram id
    field = None
    for cand in ("telegram_id", "tg_id", "user_id", "chat_id"):
        if hasattr(User, cand):
            field = cand
            break
    if not field:
        raise RuntimeError("User model must expose telegram id (telegram_id/tg_id/user_id/chat_id).")
    col = getattr(User, field)
    # attempt type-aware comparison (int vs str)
    try:
        is_str = col.property.columns[0].type.python_type is str  # type: ignore
    except Exception:
        is_str = False
    q = db.query(User).filter(col == (str(tg_id) if is_str else tg_id))
    u = q.first()
    if not u:
        u = User()
        try:
            setattr(u, field, tg_id)
        except Exception:
            setattr(u, field, str(tg_id))
        if hasattr(u, "created_at") and getattr(u, "created_at") is None:
            setattr(u, "created_at", now_utc())
        db.add(u)
        db.commit()
        db.refresh(u)
    return u

def _add_keyword(db, user, word: str) -> Optional["Keyword"]:
    word = (word or "").strip()
    if not word:
        return None
    kw = Keyword()
    # keyword text field (first found)
    for fld in ("text", "name", "word", "value", "keyword"):
        if hasattr(Keyword, fld):
            setattr(kw, fld, word)
            break
    # owner relation FK/relationship
    set_ok = False
    if hasattr(Keyword, "user"):
        try:
            setattr(kw, "user", user)
            set_ok = True
        except Exception:
            pass
    if not set_ok:
        for uf in ("id", "user_id", "pk"):
            if hasattr(user, uf):
                uid = getattr(user, uf)
                for kf in ("user_id", "uid", "owner_id"):
                    if hasattr(Keyword, kf):
                        setattr(kw, kf, uid)
                        set_ok = True
                        break
            if set_ok:
                break
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

def _get_keyword_text(k) -> str:
    for fld in ("text", "name", "word", "value", "keyword"):
        if hasattr(k, fld):
            return str(getattr(k, fld) or "")
    return ""

def _get_keyword_id(k):
    for fld in ("id", "pk"):
        if hasattr(k, fld):
            return getattr(k, fld)
    return None

def _delete_keyword(db, user, ident: str) -> int:
    ident = (ident or "").strip()
    if not ident:
        return 0
    # try numeric id
    try:
        kid_int = int(ident)
    except Exception:
        kid_int = None
    deleted = 0
    if kid_int is not None:
        q = db.query(Keyword)
        # restrict to owner if possible
        for uf in ("id", "user_id", "pk"):
            if hasattr(user, uf):
                uid = getattr(user, uf)
                for kf in ("user_id", "uid", "owner_id"):
                    if hasattr(Keyword, kf):
                        q = q.filter(getattr(Keyword, kf) == uid)
                        break
                break
        if hasattr(Keyword, "id"):
            q = q.filter(Keyword.id == kid_int)
        elif hasattr(Keyword, "pk"):
            q = q.filter(Keyword.pk == kid_int)
        for row in q.all():
            db.delete(row)
            deleted += 1
        db.commit()
        return deleted
    # delete by exact text
    q = db.query(Keyword)
    for uf in ("id", "user_id", "pk"):
        if hasattr(user, uf):
            uid = getattr(user, uf)
            for kf in ("user_id", "uid", "owner_id"):
                if hasattr(Keyword, kf):
                    q = q.filter(getattr(Keyword, kf) == uid)
                    break
            break
    for fld in ("text", "name", "word", "value", "keyword"):
        if hasattr(Keyword, fld):
            q2 = q.filter(getattr(Keyword, fld) == ident)
            rows = q2.all()
            for row in rows:
                db.delete(row)
                deleted += 1
            if deleted:
                break
    db.commit()
    return deleted

# ------------------------- Commands -------------------------

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 Welcome!\n\n"
        "I'll send you new jobs from Greek & global boards based on your keywords.\n\n"
        "• Add a keyword:  `/addkeyword lighting`\n"
        "• List keywords:  `/keywords`\n"
        "• Delete:         `/delkeyword lighting` or `/delkeyword <id>`\n"
        "• Help:           `/help`\n"
    )
    await update.message.reply_text(text, reply_markup=menu_keyboard(), disable_web_page_preview=True)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🛟 *Help*\n\n"
        "• `/start` — quick start\n"
        "• `/whoami` — show your Telegram user id\n"
        "• `/addkeyword <word>` — add a keyword (e.g. `/addkeyword lighting`)\n"
        "• `/keywords` — list your keywords\n"
        "• `/delkeyword <word>` or `/delkeyword <id>` — delete a keyword\n"
        "• `/feedstatus` — *(admin only)* sent jobs per platform in the last 24h\n\n"
        "Platforms monitored include Freelancer.com, PeoplePerHour, Malt, Workana, twago, freelancermap, "
        "YunoJuno, Worksome, Codeable, Guru, 99designs, Wripple, Toptal, plus Greek boards like Kariera, JobFind, "
        "Skywalker, Careerjet.\n"
        "_Duplicate jobs are deduped with affiliate-first preference._"
    )
    await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)

async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    uname = update.effective_user.username or "—"
    await update.message.reply_text(f"🆔 Your ID: `{uid}`\n@{uname}", parse_mode="Markdown")

async def addkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/addkeyword <word>`", parse_mode="Markdown")
        return
    word = " ".join(context.args).strip()
    if not db_available():
        await update.message.reply_text(f"(demo) ✅ Added keyword: `{word}` (no DB)", parse_mode="Markdown")
        return
    db = SessionLocal()
    try:
        u = _get_or_create_user(db, update.effective_user.id)
        k = _add_keyword(db, u, word)
        if not k:
            await update.message.reply_text("Could not save your keyword.")
            return
        await update.message.reply_text(f"✅ Added keyword: `{word}`", parse_mode="Markdown")
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
            await update.message.reply_text("You have no keywords yet. Add one with `/addkeyword ...`", parse_mode="Markdown")
            return
        lines = ["📃 *Your keywords:*"]
        for k in kws:
            kid = _get_keyword_id(k)
            ktxt = _get_keyword_text(k)
            lines.append(f"• `{kid}` — {ktxt}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        log.exception("keywords_cmd failed: %s", e)
        await update.message.reply_text("⚠️ Error while reading your keywords.")
    finally:
        db.close()

async def delkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/delkeyword <word>` or `/delkeyword <id>`", parse_mode="Markdown")
        return
    ident = " ".join(context.args).strip()
    if not db_available():
        await update.message.reply_text(f"(demo) ✅ Deleted: `{ident}` (no DB)", parse_mode="Markdown")
        return
    db = SessionLocal()
    try:
        u = _get_or_create_user(db, update.effective_user.id)
        n = _delete_keyword(db, u, ident)
        if n > 0:
            await update.message.reply_text(f"🗑️ Deleted {n} keyword(s) for `{ident}`", parse_mode="Markdown")
        else:
            await update.message.reply_text("Nothing found to delete.")
    except Exception as e:
        log.exception("delkeyword_cmd failed: %s", e)
        await update.message.reply_text("⚠️ Error while deleting keyword.")
    finally:
        db.close()

async def feedstats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # alias handler for /feedstatus and /feedstats
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
            jid = (r.job_id or "").strip()
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
        lines = ["📊 *Sent jobs by platform (last 24h):*"]
        for src, n in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
            lines.append(f"• {src}: {n}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    finally:
        try:
            db.close()
        except Exception:
            pass

# ------------------------- Application Builder -------------------------

def build_application() -> Application:
    token = (os.getenv("BOT_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is not set in environment variables.")
    app_ = ApplicationBuilder().token(token).build()

    # Handlers
    app_.add_handler(CommandHandler("start", start_cmd))
    app_.add_handler(CommandHandler("help", help_cmd))
    app_.add_handler(CommandHandler("whoami", whoami_cmd))
    app_.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app_.add_handler(CommandHandler("keywords", keywords_cmd))
    app_.add_handler(CommandHandler("delkeyword", delkeyword_cmd))
    # Admin: support both /feedstatus and /feedstats
    app_.add_handler(CommandHandler(["feedstatus", "feedstats"], feedstats_cmd))

    log.info("Handlers ready: /start, /help, /whoami, /addkeyword, /keywords, /delkeyword, /feedstatus")
    return app_


# Optional: local polling (debug)
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
