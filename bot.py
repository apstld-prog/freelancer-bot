# bot.py
import os
import json
import logging
import smtplib
from email.mime.text import MIMEText
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
    MessageHandler,
    filters,
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

# Email (SMTP)
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "77chrisap@gmail.com").strip()
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASS = os.getenv("SMTP_PASS", "").strip()
SMTP_TLS = (os.getenv("SMTP_TLS", "true").lower() != "false")

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

def get_help_text_plain(is_admin: bool) -> str:
    base = (
        "📘 How it works\n"
        "• Add keywords: /addkeyword python, lighting design, μελέτη φωτισμού\n"
        "• See your keywords: /keywords (or /mysettings)\n"
        "• Tap ⭐ Keep to store a job, 🗑 Delete to remove it from chat\n"
        "• View saved jobs: /saved\n"
    )
    if is_admin:
        admin = (
            "\n🔐 Admin only\n"
            "/stats – overall stats\n"
            "/users [page] [size] – list users\n"
            "/grant <telegram_id> <days> – set license\n"
            "/trialextend <telegram_id> <days> – extend trial\n"
            "/revoke <telegram_id> – clear license\n"
            "/reply <telegram_id> <message> – reply to user via bot (also emails you a copy)\n"
            "/admintest – send test DM+email to the admin\n"
        )
        return base + admin
    return base

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

def smtp_available() -> bool:
    return all([SMTP_HOST, SMTP_USER, SMTP_PASS, ADMIN_EMAIL])

def send_email(subject: str, body: str) -> bool:
    if not smtp_available():
        log.warning("SMTP not configured; skipping email send.")
        return False
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = SMTP_USER or "bot@localhost"
        msg["To"] = ADMIN_EMAIL
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
            if SMTP_TLS:
                s.starttls()
            if SMTP_USER and SMTP_PASS:
                s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
        return True
    except Exception as e:
        log.exception("Email send failed: %s", e)
        return False

def user_reply_kb() -> InlineKeyboardMarkup:
    # Buttons that appear under messages the admin sends to the user
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("↩️ Reply to Admin", callback_data="userreply"),
        InlineKeyboardButton("🚫 Decline", callback_data="userdecline"),
    ]])

def admin_reply_kb(user_id: int) -> InlineKeyboardMarkup:
    # Buttons under contact forwarded to admin
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("↩️ Reply", callback_data=f"adminreply:{user_id}"),
        InlineKeyboardButton("🚫 Decline", callback_data=f"admindecline:{user_id}"),
    ]])

# ───────────────────────── Telegram Application ─────────────────────────
tg_app: Optional[Application] = None


async def feedstats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    db = SessionLocal()
    try:
        since = now_utc() - timedelta(hours=24)
        rows = db.query(JobSent).filter(JobSent.created_at >= since).all()
        counts = {}
        for r in rows:
            jid = r.job_id or ""
            pref = jid.split("-",1)[0] if "-" in jid else "unknown"
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
            }.get(pref, pref)
            counts[label] = counts.get(label, 0) + 1
        if not counts:
            await update.message.reply_text("No sent jobs in the last 24h.")
            return
        lines = ["📊 Sent jobs by platform (last 24h):"]
        for src, n in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
            lines.append(f"• {src}: {n}")
        await update.message.reply_text("\n".join(lines))
    finally:
        db.close()
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
    app_.add_handler(CommandHandler("feedstats", feedstats_cmd))

    # admin cmds
    app_.add_handler(CommandHandler("admin", admin_cmd))
    app_.add_handler(CommandHandler("stats", stats_cmd))
    app_.add_handler(CommandHandler("users", users_cmd))
    app_.add_handler(CommandHandler("grant", grant_cmd))
    app_.add_handler(CommandHandler("trialextend", trialextend_cmd))
    app_.add_handler(CommandHandler("revoke", revoke_cmd))
    app_.add_handler(CommandHandler("reply", reply_cmd))
    app_.add_handler(CommandHandler("admintest", admintest_cmd))

    # callbacks
    app_.add_handler(CallbackQueryHandler(button_cb))

    # capture plain text (Contact & Admin reply & User reply flow)
    app_.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, inbound_text_handler))

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
    await update.message.reply_text(
        get_help_text_plain(is_admin(update)),
        disable_web_page_preview=True,
        reply_markup=main_menu_kb()
    )

async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    admin_line = "You are admin." if is_admin(update) else "You are a regular user."
    uname = f"@{u.username}" if u.username else "(none)"
    await update.message.reply_text(
        f"Your Telegram ID: {u.id}\nName: {u.first_name or ''}\nUsername: {uname}\n\n{admin_line}"
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
    start_dt = to_aware(u.created_at)
    now = now_utc()
    active = (trial and trial >= now) or (lic and lic >= now)
    blocked = bool(u.is_blocked)

    kw_line = ", ".join(k.keyword for k in (u.keywords or [])) or "(none)"
    countries = (u.countries or "ALL")
    proposal = u.proposal_template or "(none)"

    lines = [
        "🛠 Your Settings",
        "",
        f"• Keywords: {kw_line}",
        f"• Countries: {countries}",
        f"• Proposal template: {proposal}",
        "",
        f"🟢 Start date: {start_dt.strftime('%Y-%m-%d %H:%M:%S UTC') if start_dt else '—'}",
        f"🕑 Trial ends: {trial.strftime('%Y-%m-%d %H:%M:%S UTC') if trial else 'None'}",
        f"🧾 License until: {lic.strftime('%Y-%m-%d %H:%M:%S UTC') if lic else 'None'}",
        f"✅ Active: {'✅' if active else '❌'}",
        f"⛔ Blocked: {'❗' if blocked else '❌'}",
        "",
        "🧭 Platforms monitored:",
        "• Global: Freelancer.com, Fiverr (affiliate links), PeoplePerHour (UK), Malt (FR/EU), Workana (ES/EU/LatAm), Upwork",
        "• Greece: JobFind.gr, Skywalker.gr, Kariera.gr",
        "",
        "🧩 For extension, contact the admin."
    ]
    return "\n".join(lines)

async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        u = db.query(User).filter_by(telegram_id=str(update.effective_user.id)).first()
        if not u:
            await update.message.reply_text("No settings yet. Use /start.")
            return
        await update.message.reply_text(
            settings_text(u),
            disable_web_page_preview=True,
            reply_markup=main_menu_kb()
        )
    finally:
        db.close()

# Saved jobs — full cards
PAGE_SIZE = int(os.getenv("SAVED_PAGE_SIZE", "5"))

async def send_saved_cards(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user: User, page: int = 1):
    db = SessionLocal()
    try:
        q = db.query(SavedJob).filter_by(user_id=user.id).order_by(SavedJob.created_at.desc())
        total = q.count()
        if total == 0:
            await context.bot.send_message(chat_id, "No saved jobs yet. Tap ⭐ Keep on a job to save it.")
            return

        max_page = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        if page > max_page:
            page = max_page

        items = q.offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE).all()
        await context.bot.send_message(chat_id, f"💾 Saved jobs — page {page}/{max_page}")

        for it in items:
            job_id = it.job_id
            if job_id.startswith("freelancer-"):
                pid = job_id.split("-", 1)[1]
                data = await fl_fetch_by_id(pid)
                if not data:
                    await context.bot.send_message(chat_id, f"⚠️ Job {job_id} not available anymore.")
                    continue
                card = fl_to_card(data, matched=None)
                await context.bot.send_message(
                    chat_id,
                    job_text(card),
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                    reply_markup=card_markup(card, saved_mode=True),
                )
            else:
                await context.bot.send_message(chat_id, f"Saved: {job_id}")
    finally:
        db.close()

async def saved_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
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
            await context.bot.send_message(chat_id, "No saved jobs.")
            return
        await send_saved_cards(context, chat_id, u, page)
    finally:
        db.close()

# ───────────────────────── Admin Handlers ─────────────────────────
ADMIN_HELP = (
    "Admin commands:\n"
    "/stats – overall stats\n"
    "/users [page] [size] – list users\n"
    "/grant <telegram_id> <days> – set license\n"
    "/trialextend <telegram_id> <days> – extend trial\n"
    "/revoke <telegram_id> – clear license\n"
    "/reply <telegram_id> <message> – reply to user via bot (also emails you a copy)\n"
    "/admintest – send test DM+email to the admin\n"
)

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    await update.message.reply_text(ADMIN_HELP)

async def admintest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text="✅ Admin DM test — if you see this, DM works.")
        send_email("Freelancer Bot — Admin DM test", "This is a test message to confirm DM+email path.")
        await update.message.reply_text("Sent test DM and email to admin.")
    except Exception as e:
        log.exception("Admin test failed: %s", e)
        await update.message.reply_text(f"Admin test failed: {e}")

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
            f"Stats\n• Users: {total}\n• Active: {active}\n• With keywords: {with_keywords}"
        )
    finally:
        db.close()

async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
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
        lines = [f"Users — page {page}/{max_page} (size {size})"]
        for u in users:
            trial = to_aware(u.trial_until)
            lic = to_aware(u.access_until)
            active = (trial and trial >= now) or (lic and lic >= now)
            kw_count = len(u.keywords or [])
            lines.append(
                f"{u.telegram_id} • kw:{kw_count} • trial:{trial.isoformat() if trial else '-'} • "
                f"license:{lic.isoformat() if lic else '-'} • {'✅' if active else '❌'}"
            )
        await update.message.reply_text("\n".join(lines))
    finally:
        db.close()

async def grant_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /grant <telegram_id> <days>")
        return
    tg_str = context.args[0].strip()
    try:
        days = int(context.args[1])
    except Exception:
        await update.message.reply_text("Days must be a positive integer.")
        return
    if days <= 0:
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
        await update.message.reply_text(f"License set to {u.access_until.isoformat()} for {u.telegram_id}")
        try:
            await context.bot.send_message(chat_id=int(u.telegram_id), text=f"🔑 Your license is active until {u.access_until.isoformat()}.", reply_markup=user_reply_kb())
        except Exception as e:
            log.exception("Notify user failed: %s", e)
    finally:
        db.close()

async def trialextend_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /trialextend <telegram_id> <days>")
        return
    tg_str = context.args[0].strip()
    try:
        days = int(context.args[1])
    except Exception:
        await update.message.reply_text("Days must be a positive integer.")
        return
    if days <= 0:
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
        await update.message.reply_text(f"Trial set to {u.trial_until.isoformat()} for {u.telegram_id}")
        try:
            await context.bot.send_message(chat_id=int(u.telegram_id), text=f"🎁 Your trial is extended until {u.trial_until.isoformat()}.", reply_markup=user_reply_kb())
        except Exception as e:
            log.exception("Notify user failed: %s", e)
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
        await update.message.reply_text(f"License revoked for {u.telegram_id}")
        try:
            await context.bot.send_message(chat_id=int(u.telegram_id), text="⛔ Your license has been revoked.", reply_markup=user_reply_kb())
        except Exception as e:
            log.exception("Notify user failed: %s", e)
    finally:
        db.close()

async def reply_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /reply <telegram_id> <message>")
        return

    tg_str = context.args[0].strip()
    try:
        target_id = int(tg_str)
    except ValueError:
        await update.message.reply_text("First argument must be a numeric Telegram ID.")
        return

    full_text = update.message.text
    prefix = f"/reply {tg_str}"
    msg = full_text[len(prefix):].strip()
    if not msg:
        await update.message.reply_text("Please provide the reply message text.")
        return

    try:
        await context.bot.send_message(chat_id=target_id, text=f"💬 *Admin reply:*\n{msg}", parse_mode="Markdown", reply_markup=user_reply_kb())
        await update.message.reply_text("Reply sent ✅")
    except Exception as e:
        log.exception("Reply send failed: %s", e)
        await update.message.reply_text(f"Failed to send reply: {e}")

    subject = "Freelancer Bot — Admin reply sent"
    body = f"To user: {target_id}\n\n{msg}"
    send_email(subject, body)

# ───────────────────────── Callback buttons & Messaging flows ─────────────────────────
async def inbound_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1) Admin quick-reply flow
    if is_admin(update) and context.user_data.get("admin_reply_to"):
        target_id = context.user_data.pop("admin_reply_to")
        msg = update.message.text
        # Send to user with reply/decline buttons
        try:
            await context.bot.send_message(chat_id=target_id, text=f"💬 *Admin reply:*\n{msg}", parse_mode="Markdown", reply_markup=user_reply_kb())
            await update.message.reply_text("Reply sent ✅")
        except Exception as e:
            log.exception("Admin quick-reply failed: %s", e)
            await update.message.reply_text(f"Failed to send reply: {e}")
        # Email copy
        send_email("Freelancer Bot — Admin reply sent", f"To user: {target_id}\n\n{msg}")
        return

    # 2) User reply-to-admin flow
    if context.user_data.get("user_reply_to_admin"):
        context.user_data["user_reply_to_admin"] = False
        msg = update.message.text

        # Confirm to user
        await update.message.reply_text("✅ Your reply has been sent to the admin. You'll receive a response here.")

        # Forward to admin (with buttons so you can keep replying)
        u = update.effective_user
        uname = f"@{u.username}" if u.username else "(no username)"
        header = (
            "Reply from user\n"
            f"ID: {u.id}\n"
            f"Name: {u.first_name or ''}\n"
            f"Username: {uname}\n\n"
        )
        try:
            if ADMIN_ID:
                await context.bot.send_message(chat_id=ADMIN_ID, text=header + msg, reply_markup=admin_reply_kb(u.id))
        except Exception as e:
            log.exception("Forward user reply failed: %s", e)

        # Email copy
        send_email("Freelancer Bot — User reply", header + msg)
        return

    # 3) User contact flow
    if context.user_data.get("awaiting_contact"):
        context.user_data["awaiting_contact"] = False
        msg = update.message.text

        await update.message.reply_text("✅ Your message has been sent to the admin. You'll receive a reply here.")

        db = SessionLocal()
        try:
            urec = db.query(User).filter_by(telegram_id=str(update.effective_user.id)).first()
            user_keywords = ", ".join(k.keyword for k in (urec.keywords or [])) if urec else "(none)"
        finally:
            db.close()

        u = update.effective_user
        uname = f"@{u.username}" if u.username else "(no username)"
        header = (
            "Contact from user\n"
            f"ID: {u.id}\n"
            f"Name: {u.first_name or ''}\n"
            f"Username: {uname}\n"
            f"Keywords: {user_keywords}\n\n"
        )

        # To admin with Reply/Decline buttons
        try:
            if ADMIN_ID:
                kb = admin_reply_kb(u.id)
                await context.bot.send_message(chat_id=ADMIN_ID, text=header + msg, reply_markup=kb)
            else:
                log.warning("ADMIN_ID not set; cannot DM admin.")
        except Exception as e:
            log.exception("Failed to forward to admin: %s", e)

        # Email copy
        subject = "Freelancer Bot — New Contact message"
        body = header + msg
        send_email(subject, body)
        return

    # (fallback: ignore plain text)
    return

async def button_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data or ""
    await q.answer()

    # Admin quick actions (from forwarded Contact/User reply)
    if data.startswith("adminreply:") and is_admin(update):
        try:
            target_id = int(data.split(":", 1)[1])
            context.user_data["admin_reply_to"] = target_id
            await q.message.reply_text(f"Type your reply to user {target_id}. Your next message will be sent to them.")
        except Exception as e:
            log.exception("adminreply parse error: %s", e)
        return

    if data.startswith("admindecline:") and is_admin(update):
        try:
            target_id = int(data.split(":", 1)[1])
            text = ("Hello! The admin has reviewed your message and cannot proceed at this time.\n"
                    "Thank you for reaching out.")
            try:
                await context.bot.send_message(chat_id=target_id, text=text, reply_markup=user_reply_kb())
            except Exception as e:
                log.exception("Decline send failed: %s", e)
            send_email("Freelancer Bot — Admin decline sent", f"To user: {target_id}\n\n{text}")
            await q.message.reply_text("Decline sent ✅")
        except Exception as e:
            log.exception("admindecline parse error: %s", e)
        return

    # User actions under admin-sent messages
    if data == "userreply":
        # Put the user in reply-to-admin mode
        context.user_data["user_reply_to_admin"] = True
        await q.message.reply_text("✍️ Please type your reply to the admin. It will be forwarded immediately.")
        return

    if data == "userdecline":
        # Politely close the thread for the user
        await q.message.reply_text("Thanks! If you need anything else, you can press 📞 Contact from the main menu.")
        # Optionally notify admin
        try:
            if ADMIN_ID:
                u = update.effective_user
                await context.bot.send_message(chat_id=ADMIN_ID, text=f"User {u.id} declined further replies.")
        except Exception:
            pass
        return

    # Regular opens from main menu
    if data.startswith("open:"):
        where = data.split(":", 1)[1]
        if where == "addkw":
            await q.message.reply_text(
                "Add keywords with: /addkeyword python, lighting design, μελέτη φωτισμού"
            )
        elif where == "settings":
            db = SessionLocal()
            try:
                u = db.query(User).filter_by(telegram_id=str(update.effective_user.id)).first()
                if u:
                    await q.message.reply_text(
                        settings_text(u), disable_web_page_preview=True
                    )
            finally:
                db.close()
        elif where == "help":
            await q.message.reply_text(
                get_help_text_plain(is_admin(update)),
                disable_web_page_preview=True
            )
        elif where == "contact":
            context.user_data["awaiting_contact"] = True
            await q.message.reply_text(
                "✍️ Please type your message for the admin. I’ll forward it right away."
            )
        elif where == "saved":
            db = SessionLocal()
            try:
                u = db.query(User).filter_by(telegram_id=str(update.effective_user.id)).first()
                if u:
                    await send_saved_cards(context, q.message.chat.id, u, page=1)
            finally:
                db.close()
        return

    # Save / Unsave / Dismiss for job cards
    if data.startswith("save:"):
        job_id = data.split(":", 1)[1]
        db = SessionLocal()
        try:
            u = db.query(User).filter_by(telegram_id=str(update.effective_user.id)).first()
            if not u:
                return
            exists = db.query(SavedJob).filter_by(user_id=u.id, job_id=job_id).first()
            if exists is None:
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
