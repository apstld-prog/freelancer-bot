# bot.py
# -*- coding: utf-8 -*-
"""
Telegram bot (python-telegram-bot v20+)

Layout: matches the screenshot
- Welcome card (English)
- Big inline buttons: Add Keywords, Settings, Help, Saved, Contact, Admin
- Features block after the menu
- Keywords persistence: /addkeyword, /keywords, /delkeyword
- Admin stats: /feedstatus (alias: /feedstats)
"""

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

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

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

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

def _get_or_create_user(db, tg_id: int):
    field = None
    for cand in ("telegram_id", "tg_id", "user_id", "chat_id"):
        if hasattr(User, cand):
            field = cand
            break
    if not field:
        raise RuntimeError("User model must expose telegram id (telegram_id/tg_id/user_id/chat_id).")
    col = getattr(User, field)

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

def _add_keyword(db, user, word: str):
    word = (word or "").strip()
    if not word:
        return None
    kw = Keyword()
    for fld in ("text", "name", "word", "value", "keyword"):
        if hasattr(Keyword, fld):
            setattr(kw, fld, word)
            break

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


# ---------- UI (matches screenshot) ----------

def main_menu_keyboard() -> InlineKeyboardMarkup:
    # 3 rows × 2 buttons (as in screenshot)
    rows = [
        [
            InlineKeyboardButton("➕ Add Keywords", callback_data="noop"),
            InlineKeyboardButton("⚙️ Settings", callback_data="noop"),
        ],
        [
            InlineKeyboardButton("🆘 Help", callback_data="noop"),
            InlineKeyboardButton("💾 Saved", callback_data="noop"),
        ],
        [
            InlineKeyboardButton("📞 Contact", callback_data="noop"),
            InlineKeyboardButton("👑 Admin", callback_data="noop"),
        ],
    ]
    return InlineKeyboardMarkup(rows)

WELCOME_TEXT = (
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

def settings_card_text(user_keywords: List[str]) -> str:
    # Minimal settings card like your screenshot. Extend with more fields if you store them in DB.
    kw_display = ", ".join(user_keywords) if user_keywords else "—"
    trial_until = os.getenv("TRIAL_UNTIL", "None")
    license_until = os.getenv("LICENSE_UNTIL", "None")
    active = "✅"
    blocked = "✅" if os.getenv("BLOCKED", "false").lower() == "true" else "❌"

    return (
        "🛠️ <b>Your Settings</b>\n"
        f"• Keywords: {kw_display}\n"
        "• Countries: ALL\n"
        "• Proposal template: (none)\n\n"
        "🟢 Start date: —\n"
        f"⏳ Trial ends: {trial_until}\n"
        f"🔑 License until: {license_until}\n"
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


# ---------- Commands ----------

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1) Welcome card with menu
    await update.message.reply_text(WELCOME_TEXT, reply_markup=main_menu_keyboard(), disable_web_page_preview=True)

    # 2) Features block
    await update.message.reply_text(FEATURES_TEXT, disable_web_page_preview=True)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🧭 <b>Help / How it works</b>\n\n"
        "1) Add keywords with <code>/addkeyword python</code>\n"
        "2) List your keywords with <code>/keywords</code>\n"
        "3) Delete with <code>/delkeyword &lt;word|id&gt;</code>\n"
        "4) Check stats (admin): <code>/feedstatus</code>\n\n"
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
        user_kw = []
        if kws:
            lines = ["📃 <b>Your keywords</b>"]
            for k in kws:
                kid = _get_keyword_id(k)
                ktxt = _get_keyword_text(k)
                user_kw.append(ktxt)
                lines.append(f"• <code>{kid}</code> — {ktxt}")
            await update.message.reply_text("\n".join(lines), parse_mode="HTML")
        else:
            await update.message.reply_text("You have no keywords yet. Add one with <code>/addkeyword ...</code>", parse_mode="HTML")

        # Also show a settings-style card like the screenshot
        await update.message.reply_text(settings_card_text(user_kw), parse_mode="HTML", disable_web_page_preview=True)
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
        # small local helper (already above)
        deleted = 0
        try:
            # numeric id?
            kid = int(ident)
            q = db.query(Keyword)
            # restrict to owner if possible
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
            # delete by exact text
            q = db.query(Keyword)
            for uf in ("id", "user_id", "pk"):
                if hasattr(u, uf):
                    uid = getattr(u, uf)
                    for kf in ("user_id", "uid", "owner_id"):
                        if hasattr(Keyword, kf):
                            q = q.filter(getattr(Keyword, kf) == uid)
                            break
                    break
            for fld in ("text", "name", "word", "value", "keyword"):
                if hasattr(Keyword, fld):
                    rows = q.filter(getattr(Keyword, fld) == ident).all()
                    for r in rows:
                        db.delete(r); deleted += 1
                    if deleted:
                        break
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

    app_.add_handler(CommandHandler("start", start_cmd))
    app_.add_handler(CommandHandler("help", help_cmd))
    app_.add_handler(CommandHandler("whoami", whoami_cmd))
    app_.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app_.add_handler(CommandHandler("keywords", keywords_cmd))
    app_.add_handler(CommandHandler("delkeyword", delkeyword_cmd))
    app_.add_handler(CommandHandler(["feedstatus", "feedstats"], feedstatus_cmd))

    log.info("Handlers ready: /start, /help, /whoami, /addkeyword, /keywords, /delkeyword, /feedstatus")
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
