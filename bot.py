# bot.py
import os
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Tuple

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from db import (
    ensure_schema,
    SessionLocal,
    User,
    Keyword,
    JobSent,
    SavedJob,
)

# ───────────────────────── Logging ─────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [bot] %(levelname)s: %(message)s")
log = logging.getLogger("bot")

# ───────────────────────── Env ─────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "hook-secret-777")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
TRIAL_DAYS = int(os.getenv("TRIAL_DAYS", "10"))
FREELANCER_REF_CODE = os.getenv("FREELANCER_REF_CODE", "").strip()

# ───────────────────────── FastAPI ─────────────────────────
app = FastAPI()

# ───────────────────────── Time helpers ─────────────────────────
UTC = timezone.utc
def now_utc() -> datetime:
    return datetime.now(UTC)

def to_aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)

# ───────────────────────── DB ensure ─────────────────────────
ensure_schema()

# ───────────────────────── Currency helpers ─────────────────────────
DEFAULT_USD_RATES = {
    "USD": 1.0, "EUR": 1.07, "GBP": 1.25, "AUD": 0.65, "CAD": 0.73, "CHF": 1.10,
    "SEK": 0.09, "NOK": 0.09, "DKK": 0.14, "PLN": 0.25, "RON": 0.22, "BGN": 0.55,
    "TRY": 0.03, "MXN": 0.055, "BRL": 0.19, "INR": 0.012,
}
def load_usd_rates() -> Dict[str, float]:
    raw = os.getenv("FX_USD_RATES", "").strip()
    if not raw:
        return DEFAULT_USD_RATES
    try:
        data = json.loads(raw)
        safe = {k.upper(): float(v) for k, v in data.items()}
        safe["USD"] = 1.0
        return {**DEFAULT_USD_RATES, **safe}
    except Exception:
        return DEFAULT_USD_RATES
USD_RATES = load_usd_rates()

CURRENCY_SYMBOLS = {
    "USD": "$", "EUR": "€", "GBP": "£",
    "AUD": "A$", "CAD": "C$", "CHF": "CHF",
    "SEK": "SEK", "NOK": "NOK", "DKK": "DKK",
    "PLN": "zł", "RON": "lei", "BGN": "лв",
    "TRY": "₺", "MXN": "MX$", "BRL": "R$", "INR": "₹",
}
def fmt_local_budget(minb: float, maxb: float, code: Optional[str]) -> str:
    s = CURRENCY_SYMBOLS.get((code or "").upper(), "")
    if minb or maxb:
        if s:
            return f"{minb:.0f}–{maxb:.0f} {s}"
        return f"{minb:.0f}–{maxb:.0f} {(code or '').upper()}"
    return "—"
def to_usd(minb: float, maxb: float, code: Optional[str]) -> Optional[Tuple[float, float]]:
    c = (code or "USD").upper()
    rate = USD_RATES.get(c)
    if not rate:
        return None
    return minb * rate, maxb * rate
def fmt_usd_line(min_usd: float, max_usd: float) -> str:
    return f"~ ${min_usd:.0f}–${max_usd:.0f} USD"

# ───────────────────────── Freelancer helpers ─────────────────────────
HTTP_TIMEOUT = 20.0

async def fl_fetch_by_id(pid: str) -> Optional[Dict]:
    url = (
        "https://www.freelancer.com/api/projects/0.1/projects/"
        f"{pid}/?full_description=true&job_details=true&compact=true"
    )
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers={"Accept": "application/json"}) as client:
        r = await client.get(url)
        if r.status_code != 200:
            return None
        data = r.json()
    return (data or {}).get("result") or None

def fl_to_card(p: Dict, matched: Optional[List[str]] = None) -> Dict:
    pid = str(p.get("id"))
    title = p.get("title") or "Untitled"
    type_ = "Fixed" if p.get("type") == "fixed" else ("Hourly" if p.get("type") == "hourly" else "Unknown")

    budget = p.get("budget") or {}
    minb = float(budget.get("minimum") or 0)
    maxb = float(budget.get("maximum") or 0)
    cur = budget.get("currency") or {}
    code = (cur.get("code") or "USD").upper() if isinstance(cur, dict) else "USD"

    bids = p.get("bid_stats", {}).get("bid_count", 0)
    time_submitted = p.get("time_submitted")
    posted = "now"
    if isinstance(time_submitted, (int, float)):
        age_sec = max(0, int(now_utc().timestamp() - time_submitted))
        posted = (
            f"{age_sec}s ago" if age_sec < 60 else
            f"{age_sec//60}m ago" if age_sec < 3600 else
            f"{age_sec//3600}h ago" if age_sec < 86400 else
            f"{age_sec//86400}d ago"
        )

    base_url = f"https://www.freelancer.com/projects/{pid}"
    sep = "&" if "?" in base_url else "?"
    url = f"{base_url}{sep}f={FREELANCER_REF_CODE}" if FREELANCER_REF_CODE else base_url

    desc = (p.get("description") or "").strip().replace("\r", " ").replace("\n", " ")
    if len(desc) > 220:
        desc = desc[:217] + "…"

    local_line = fmt_local_budget(minb, maxb, code)
    usd_pair = to_usd(minb, maxb, code)
    usd_line = fmt_usd_line(*usd_pair) if usd_pair else None

    return {
        "id": f"freelancer-{pid}",
        "source": "Freelancer",
        "title": title,
        "type": type_,
        "budget_local": local_line,
        "budget_usd": usd_line,
        "bids": bids,
        "posted": posted,
        "description": desc,
        "proposal_url": url,
        "original_url": url,
        "matched": matched or [],
    }

def job_text(card: Dict) -> str:
    lines = [
        f"*{card['title']}*",
        "",
        f"👤 Source: *{card['source']}*",
        f"🧾 Type: *{card['type']}*",
        f"💰 Budget: *{card['budget_local']}*",
    ]
    if card.get("budget_usd"):
        lines.append(f"💵 {card['budget_usd']}")
    lines += [
        f"📨 Bids: *{card['bids']}*",
        f"🕒 Posted: *{card['posted']}*",
        "",
        card.get("description") or "",
    ]
    if card.get("matched"):
        lines += ["", f"_Matched:_ {', '.join(card['matched'])}"]
    return "\n".join(lines)

def card_markup(card: Dict, saved_mode: bool = False) -> InlineKeyboardMarkup:
    rows = [[
        InlineKeyboardButton("💼 Proposal", url=card["proposal_url"]),
        InlineKeyboardButton("🔗 Original", url=card["original_url"]),
    ]]
    if saved_mode:
        rows.append([InlineKeyboardButton("🗑 Remove from Saved", callback_data=f"unsave:{card['id']}")])
    else:
        rows.append([
            InlineKeyboardButton("⭐ Keep", callback_data=f"save:{card['id']}"),
            InlineKeyboardButton("🗑 Delete", callback_data=f"dismiss:{card['id']}"),
        ])
    return InlineKeyboardMarkup(rows)

# ───────────────────────── Texts & Menu ─────────────────────────
WELCOME_FULL = (
    "👋 *Welcome to Freelancer Alert Bot!*\n\n"
    "🎁 You have a *10-day free trial*.\n"
    "Automatically finds matching freelance jobs from top platforms and sends you instant alerts with affiliate-safe links.\n\n"
    "✨ *Features*\n"
    "• Realtime job alerts (Freelancer API)\n"
    "• Affiliate-wrapped *Proposal* & *Original* links\n"
    "• Budget shown + USD conversion\n"
    "• ⭐ *Keep* / 🗑 *Delete* buttons\n"
    "• 10-day free trial, extend via admin\n"
    "• Multi-keyword search (single/all modes)\n"
    "• Platforms by country (incl. GR boards)\n\n"
    "Use /help to see all commands."
)
HELP_TEXT = (
    "📘 *How it works*\n"
    "• Add keywords with `/addkeyword python, lighting design, μελέτη φωτισμού`\n"
    "• See filters with `/keywords` or `/mysettings`\n"
    "• Tap ⭐ *Keep* to store a job, 🗑 *Delete* to remove it from chat\n"
    "• View saved jobs with `/saved` — full cards\n"
    "• Admin can extend licenses manually"
)

def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Add Keywords", callback_data="open:addkw"),
            InlineKeyboardButton("⚙️ Settings", callback_data="open:settings"),
        ],
        [
            InlineKeyboardButton("📚 Help", callback_data="open:help"),
            InlineKeyboardButton("📞 Contact", callback_data="open:contact"),
        ],
        [
            InlineKeyboardButton("💾 Saved", callback_data="open:saved"),
        ],
    ])

# ───────────────────────── Util ─────────────────────────
def is_admin(update: Update) -> bool:
    u = update.effective_user
    return bool(ADMIN_ID) and u and u.id == ADMIN_ID

def parse_int(s: str) -> Optional[int]:
    try:
        return int(s)
    except Exception:
        return None

# ───────────────────────── Telegram Application ─────────────────────────
tg_app: Optional[Application] = None

def build_application() -> Application:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN not set")
    app_ = ApplicationBuilder().token(BOT_TOKEN).build()

    # user cmds
    app_.add_handler(CommandHandler("start", start_cmd))
    app_.add_handler(CommandHandler("help", help_cmd))
    app_.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app_.add_handler(CommandHandler("keywords", keywords_cmd))
    app_.add_handler(CommandHandler("delkeyword", delkeyword_cmd))
    app_.add_handler(CommandHandler("clearkeywords", clearkeywords_cmd))
    app_.add_handler(CommandHandler("mysettings", mysettings_cmd))
    app_.add_handler(CommandHandler("saved", saved_cmd))
    app_.add_handler(CommandHandler("whoami", whoami_cmd))

    # admin cmds
    app_.add_handler(CommandHandler("admin", admin_cmd))
    app_.add_handler(CommandHandler("stats", stats_cmd))
    app_.add_handler(CommandHandler("users", users_cmd))
    app_.add_handler(CommandHandler("grant", grant_cmd))
    app_.add_handler(CommandHandler("trialextend", trialextend_cmd))
    app_.add_handler(CommandHandler("revoke", revoke_cmd))

    app_.add_handler(CallbackQueryHandler(button_cb))

    return app_

# ───────────────────────── User Handlers ─────────────────────────
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        tg_id = update.effective_user.id
        db = SessionLocal()
        try:
            user = db.query(User).filter_by(telegram_id=str(tg_id)).first()
            if not user:
                user = User(telegram_id=str(tg_id))
                db.add(user)
            if not user.trial_until:
                user.trial_until = now_utc() + timedelta(days=TRIAL_DAYS)
            db.commit()
        finally:
            db.close()

        await update.message.reply_text(
            WELCOME_FULL, parse_mode="Markdown", reply_markup=main_menu_kb()
        )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown", reply_markup=main_menu_kb())

async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    admin_line = "👤 You are *admin*." if ADMIN_ID and u.id == ADMIN_ID else "👤 You are a regular user."
    await update.message.reply_text(
        f"🆔 Your Telegram ID: `{u.id}`\n"
        f"👤 Name: {u.first_name or ''}\n"
        f"{admin_line}",
        parse_mode="Markdown"
    )

def split_keywords(raw: str) -> List[str]:
    if not raw:
        return []
    parts = [p.strip() for p in raw.replace(";", ",").split(",")]
    parts = [p for p in parts if p]
    seen = set()
    out = []
    for p in parts:
        low = p.lower()
        if low not in seen:
            out.append(p)
            seen.add(low)
    return out

async def addkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(telegram_id=str(update.effective_user.id)).first()
        if not user:
            user = User(telegram_id=str(update.effective_user.id), trial_until=now_utc() + timedelta(days=TRIAL_DAYS))
            db.add(user)
            db.commit()

        text = " ".join(context.args) if context.args else (update.message.text.partition(" ")[2] or "")
        kws = split_keywords(text)
        if not kws:
            await update.message.reply_text("Please provide keywords separated by commas.")
            return

        existing = {k.keyword.lower() for k in (user.keywords or [])}
        added = 0
        for kw in kws:
            if kw.lower() in existing:
                continue
            db.add(Keyword(user_id=user.id, keyword=kw))
            added += 1
        db.commit()
        await update.message.reply_text(f"Added {added} keyword(s).")
    finally:
        db.close()

async def keywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(telegram_id=str(update.effective_user.id)).first()
        words = ", ".join(k.keyword for k in (user.keywords or [])) if user else "(none)"
        await update.message.reply_text(f"Your keywords: {words}")
    finally:
        db.close()

async def delkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /delkeyword <kw>")
        return
    kw = " ".join(context.args).strip().lower()
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(telegram_id=str(update.effective_user.id)).first()
        if not user:
            await update.message.reply_text("No keywords.")
            return
        deleted = 0
        for k in list(user.keywords or []):
            if k.keyword.lower() == kw:
                db.delete(k)
                deleted += 1
        db.commit()
        await update.message.reply_text(f"Deleted {deleted} entries.")
    finally:
        db.close()

async def clearkeywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(telegram_id=str(update.effective_user.id)).first()
        if not user or not user.keywords:
            await update.message.reply_text("No keywords to clear.")
            return
        for k in list(user.keywords):
            db.delete(k)
        db.commit()
        await update.message.reply_text("All keywords cleared.")
    finally:
        db.close()

def settings_text(u: User) -> str:
    trial = to_aware(u.trial_until)
    lic = to_aware(u.access_until)
    now = now_utc()
    active = (trial and trial >= now) or (lic and lic >= now)
    trial_line = f"Trial until: *{trial.isoformat()}*" if trial else "Trial until: *None*"
    lic_line = f"License until: *{lic.isoformat()}*" if lic else "License until: *None*"
    kw_line = ", ".join(k.keyword for k in (u.keywords or [])) or "(none)"
    return (
        "🛠 *Your Settings*\n\n"
        f"• Keywords: {kw_line}\n"
        f"• {trial_line}\n"
        f"• {lic_line}\n"
        f"• Active: {'✅' if active else '❌'}"
    )

async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        u = db.query(User).filter_by(telegram_id=str(update.effective_user.id)).first()
        if not u:
            await update.message.reply_text("No settings yet. Use /start.")
            return
        await update.message.reply_text(settings_text(u), parse_mode="Markdown", reply_markup=main_menu_kb())
    finally:
        db.close()

PAGE_SIZE = int(os.getenv("SAVED_PAGE_SIZE", "5"))

async def saved_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    page = 1
    if context.args:
        try:
            page = max(1, int(context.args[0]))
        except ValueError:
            page = 1

    db = SessionLocal()
    try:
        u = db.query(User).filter_by(telegram_id=str(update.effective_user.id)).first()
        if not u:
            await update.message.reply_text("No saved jobs.")
            return
        q = db.query(SavedJob).filter_by(user_id=u.id).order_by(SavedJob.created_at.desc())
        total = q.count()
        if total == 0:
            await update.message.reply_text("No saved jobs yet. Tap ⭐ *Keep* on a job to save it.", parse_mode="Markdown")
            return

        max_page = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        if page > max_page:
            page = max_page

        items = q.offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE).all()

        await update.message.reply_text(f"💾 Saved jobs — page {page}/{max_page}")

        for it in items:
            job_id = it.job_id
            if job_id.startswith("freelancer-"):
                pid = job_id.split("-", 1)[1]
                data = await fl_fetch_by_id(pid)
                if not data:
                    await update.message.reply_text(f"⚠️ Job {job_id} not available anymore.")
                    continue
                card = fl_to_card(data, matched=None)
                await update.message.reply_text(
                    job_text(card),
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                    reply_markup=card_markup(card, saved_mode=True),
                )
            else:
                await update.message.reply_text(f"Saved: {job_id}")
    finally:
        db.close()

# ───────────────────────── Admin Handlers ─────────────────────────
ADMIN_HELP = (
    "*Admin commands:*\n"
    "/stats – overall stats\n"
    "/users [page] [size] – list users\n"
    "/grant <telegram_id> <days> – extend/set license\n"
    "/trialextend <telegram_id> <days> – extend trial\n"
    "/revoke <telegram_id> – clear license\n"
)

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    await update.message.reply_text(ADMIN_HELP, parse_mode="Markdown")

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    db = SessionLocal()
    try:
        users = db.query(User).all()
        total = len(users)
        now = now_utc()
        active = 0
        with_keywords = 0
        for u in users:
            if (to_aware(u.trial_until) and to_aware(u.trial_until) >= now) or \
               (to_aware(u.access_until) and to_aware(u.access_until) >= now):
                active += 1
            if u.keywords:
                with_keywords += 1
        await update.message.reply_text(
            f"*Stats*\n• Users: {total}\n• Active: {active}\n• With keywords: {with_keywords}",
            parse_mode="Markdown"
        )
    finally:
        db.close()

async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    # /users [page] [size]
    page = 1
    size = 20
    if context.args:
        if len(context.args) >= 1 and context.args[0].isdigit():
            page = max(1, int(context.args[0]))
        if len(context.args) >= 2 and context.args[1].isdigit():
            size = max(1, min(100, int(context.args[1])))

    db = SessionLocal()
    try:
        q = db.query(User).order_by(User.created_at.desc())
        total = q.count()
        max_page = max(1, (total + size - 1) // size)
        if page > max_page:
            page = max_page
        users = q.offset((page - 1) * size).limit(size).all()

        now = now_utc()
        lines = [f"*Users* — page {page}/{max_page} (size {size})"]
        for u in users:
            trial = to_aware(u.trial_until)
            lic = to_aware(u.access_until)
            active = (trial and trial >= now) or (lic and lic >= now)
            kw_count = len(u.keywords or [])
            lines.append(
                f"`{u.telegram_id}` • kw:{kw_count} • trial:{trial.isoformat() if trial else '-'} • "
                f"license:{lic.isoformat() if lic else '-'} • {'✅' if active else '❌'}"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    finally:
        db.close()

async def grant_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /grant <telegram_id> <days>")
        return
    tg_str = context.args[0].strip()
    days = parse_int(context.args[1])
    if not days or days <= 0:
        await update.message.reply_text("Days must be a positive integer.")
        return

    db = SessionLocal()
    try:
        u = db.query(User).filter_by(telegram_id=str(tg_str)).first()
        if not u:
            await update.message.reply_text("User not found.")
            return
        now = now_utc()
        base = to_aware(u.access_until) or now
        if base < now:
            base = now
        u.access_until = base + timedelta(days=days)
        db.commit()
        await update.message.reply_text(f"License set to {u.access_until.isoformat()} for `{u.telegram_id}`", parse_mode="Markdown")
        # ενημέρωση χρήστη
        try:
            await tg_app.bot.send_message(chat_id=int(u.telegram_id), text=f"🔑 Your license is active until {u.access_until.isoformat()}.")
        except Exception:
            pass
    finally:
        db.close()

async def trialextend_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /trialextend <telegram_id> <days>")
        return
    tg_str = context.args[0].strip()
    days = parse_int(context.args[1])
    if not days or days <= 0:
        await update.message.reply_text("Days must be a positive integer.")
        return

    db = SessionLocal()
    try:
        u = db.query(User).filter_by(telegram_id=str(tg_str)).first()
        if not u:
            await update.message.reply_text("User not found.")
            return
        now = now_utc()
        base = to_aware(u.trial_until) or now
        if base < now:
            base = now
        u.trial_until = base + timedelta(days=days)
        db.commit()
        await update.message.reply_text(f"Trial set to {u.trial_until.isoformat()} for `{u.telegram_id}`", parse_mode="Markdown")
        try:
            await tg_app.bot.send_message(chat_id=int(u.telegram_id), text=f"🎁 Your trial is extended until {u.trial_until.isoformat()}.")
        except Exception:
            pass
    finally:
        db.close()

async def revoke_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /revoke <telegram_id>")
        return
    tg_str = context.args[0].strip()
    db = SessionLocal()
    try:
        u = db.query(User).filter_by(telegram_id=str(tg_str)).first()
        if not u:
            await update.message.reply_text("User not found.")
            return
        u.access_until = None
        db.commit()
        await update.message.reply_text(f"License revoked for `{u.telegram_id}`", parse_mode="Markdown")
        try:
            await tg_app.bot.send_message(chat_id=int(u.telegram_id), text="⛔ Your license has been revoked.")
        except Exception:
            pass
    finally:
        db.close()

# ───────────────────────── Callback buttons ─────────────────────────
async def button_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data or ""
    await q.answer()

    if data.startswith("open:"):
        where = data.split(":", 1)[1]
        if where == "addkw":
            await q.message.reply_text(
                "Add keywords:\n`/addkeyword python, lighting design, μελέτη φωτισμού`",
                parse_mode="Markdown"
            )
        elif where == "settings":
            db = SessionLocal()
            try:
                u = db.query(User).filter_by(telegram_id=str(update.effective_user.id)).first()
                if u:
                    await q.message.reply_text(settings_text(u), parse_mode="Markdown")
            finally:
                db.close()
        elif where == "help":
            await q.message.reply_text(HELP_TEXT, parse_mode="Markdown")
        elif where == "contact":
            await q.message.reply_text("Contact admin: please send your message here; the admin will reach out.")
        elif where == "saved":
            await saved_cmd(update, context)
        return

    if data.startswith("save:"):
        job_id = data.split(":", 1)[1]
        db = SessionLocal()
        try:
            u = db.query(User).filter_by(telegram_id=str(update.effective_user.id)).first()
            if not u:
                return
            exists = db.query(SavedJob).filter_by(user_id=u.id, job_id=job_id).first()
            if not exists:
                db.add(SavedJob(user_id=u.id, job_id=job_id))
                db.commit()
            await q.answer("Saved ✅", show_alert=False)
        finally:
            db.close()
        return

    if data.startswith("unsave:"):
        job_id = data.split(":", 1)[1]
        db = SessionLocal()
        try:
            u = db.query(User).filter_by(telegram_id=str(update.effective_user.id)).first()
            if not u:
                return
            row = db.query(SavedJob).filter_by(user_id=u.id, job_id=job_id).first()
            if row:
                db.delete(row)
                db.commit()
            await q.answer("Removed from saved.", show_alert=False)
            try:
                await q.message.delete()
            except Exception:
                pass
        finally:
            db.close()
        return

    if data.startswith("dismiss:"):
        try:
            await q.message.delete()
        except Exception:
            pass
        return

# ───────────────────────── Webhook lifecycle ─────────────────────────
tg_app: Optional[Application] = None

def get_webhook_url() -> str:
    if not BASE_URL:
        raise RuntimeError("BASE_URL is not set")
    return f"{BASE_URL}/webhook/{WEBHOOK_SECRET}"

@app.on_event("startup")
async def on_startup():
    global tg_app
    tg_app = build_application()
    await tg_app.initialize()
    await tg_app.start()
    url = get_webhook_url()
    await tg_app.bot.delete_webhook(drop_pending_updates=True)
    await tg_app.bot.set_webhook(url=url, allowed_updates=Update.ALL_TYPES)
    me = await tg_app.bot.get_me()
    log.info("PTB app initialized. Webhook set to %s (bot=%s).", url, me.username)

@app.on_event("shutdown")
async def on_shutdown():
    if tg_app:
        await tg_app.bot.delete_webhook()
        await tg_app.stop()
        await tg_app.shutdown()
        log.info("PTB app stopped.")

@app.post(f"/webhook/{WEBHOOK_SECRET}")
async def telegram_webhook(request: Request):
    data = await request.json()
    if tg_app is None:
        return PlainTextResponse("App not ready", status_code=503)
    try:
        update = Update.de_json(data, tg_app.bot)
        logging.info("Webhook update received.")
        await tg_app.process_update(update)
    except Exception as e:
        logging.exception("Webhook processing error: %s", e)
    return PlainTextResponse("OK")

@app.get("/")
async def root():
    return PlainTextResponse("OK")

# ───────────────────────── Entrypoint ─────────────────────────
if __name__ == "__main__":
    uvicorn.run("bot:app", host="0.0.0.0", port=int(os.getenv("PORT", "10000")), reload=False)
