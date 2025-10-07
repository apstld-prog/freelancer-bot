# bot.py
# -------------------------------------------------
# Freelancer Alert Bot (stable /start + /selftest)
# - Δεν αλλάζει το υπάρχον στήσιμο των κουμπιών.
# - Δουλεύει με sync SQLAlchemy SessionLocal.
# - Πιο καθαρά logs στο webhook, για να φαίνεται τι φτάνει.
# - Αν σταλεί "Start" ως απλό text => τρέχει start_cmd.
# - Περιμένει: BOT_TOKEN, WEBHOOK_URL, WEBHOOK_SECRET, ADMIN_TG_ID
# -------------------------------------------------

import os
import json
import traceback
from datetime import timedelta

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ----- DB (sync) -----
from db import (
    SessionLocal,
    now_utc,
    User,
    Keyword,
    Job,
    SavedJob,
    JobSent,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "hook-secret-777")
ADMIN_TG_ID = os.getenv("ADMIN_TG_ID")

# ------------- utils -------------
def db_open():
    return SessionLocal()

def is_admin(uid) -> bool:
    return ADMIN_TG_ID and str(uid) == str(ADMIN_TG_ID)

def md(text: str) -> str:
    if not text:
        return ""
    return (
        text.replace("_", "\\_")
        .replace("*", "\\*")
        .replace("[", "\\[")
        .replace("`", "\\`")
    )

# ------------- UI -------------
def main_menu_kb() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton("Keywords"), KeyboardButton("Saved Jobs")],
        [KeyboardButton("Settings"), KeyboardButton("Help")],
        [KeyboardButton("Contact")],
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def help_text(show_admin: bool) -> str:
    base = [
        "*Help*",
        "• Use the main buttons:",
        "  - *Keywords*, *Saved Jobs*, *Settings*, *Contact*.",
        "",
        "Commands:",
        "• /start – show menu (+ start 10-day trial for new users)",
        "• /menu – show menu",
        "• /selftest – quick test",
        "• /help – this",
    ]
<<<<<<< HEAD
    if show_admin:
        base += [
            "",
            "*Admin*",
            "• /admin – list users",
            "• /grant <telegram_id> <days>",
            "• /feedsstatus – last worker stats",
        ]
    return "\n".join(base)
=======
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
>>>>>>> ce3fc6e (Auto commit Tue-10-07 15-23)

def settings_text(u: User) -> str:
    now = now_utc()
    def fmt(dt): return dt.strftime("%Y-%m-%d %H:%M UTC") if dt else "—"
    active = ((u.trial_until and u.trial_until >= now) or (u.access_until and u.access_until >= now))
    keys = ", ".join(k.keyword for k in (u.keywords or [])) if u.keywords else "(none)"
    lines = [
        "🛠 *Your Settings*",
        f"• Keywords: {md(keys)}",
        "• Countries: ALL",
        "• Proposal template: (none)",
        "",
        f"🟢 Start date: {fmt(getattr(u,'started_at', None))}",
        f"⏳ Trial ends: {fmt(u.trial_until)}",
        f"🪪 License until: {fmt(u.access_until)}",
        f"✅ Active: {'✅' if active else '❌'}",
        f"⛔ Blocked: {'❌' if not u.is_blocked else '✅'}",
        "",
        "🗂 *Platforms monitored:*",
        "• Global: Freelancer.com (affiliate links), PeoplePerHour, Malt, Workana, Guru, 99designs, Toptal*, Codeable*, YunoJuno*, Worksome*, twago, freelancermap",
        "  (* referral/curated platforms)",
        "• Greece: JobFind.gr, Skywalker.gr, Kariera.gr",
        "",
        "🆘 For extension, contact the admin.",
    ]
    return "\n".join(lines)

# -------- Contact (user -> admin, reply) --------
def admin_reply_kb(sender_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Reply", callback_data=f"admin_reply:{sender_id}"),
          InlineKeyboardButton("Decline", callback_data=f"admin_decline:{sender_id}")]]
    )

async def route_user_message_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not ADMIN_TG_ID:
        await update.message.reply_text("Admin not configured.")
        return
    u = update.effective_user
    header = f"✉️ *User Message*\nFrom: `{u.full_name or ''}` (@{u.username or '—'})\nTG ID: `{u.id}`\n\n"
    await context.bot.send_message(
        chat_id=int(ADMIN_TG_ID),
        text=header + md(update.message.text or ""),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=admin_reply_kb(str(u.id)),
    )
    await update.message.reply_text("✅ Sent to admin. You’ll get the reply here.")

async def handle_admin_reply_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(update.effective_user.id):
        return
    data = q.data or ""
    if data.startswith("admin_reply:"):
        target = data.split(":", 1)[1]
        context.user_data["reply_target"] = target
        await q.message.reply_text(f"Type your reply to `{target}` and send.", parse_mode=ParseMode.MARKDOWN)
    elif data.startswith("admin_decline:"):
        target = data.split(":", 1)[1]
        try:
            await context.bot.send_message(int(target), "❌ Admin declined to respond.")
        except Exception:
            pass
        await q.message.reply_text(f"Declined (user {target} notified).")

async def admin_sends_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    target = context.user_data.get("reply_target")
    if not target:
        return
    try:
        await context.bot.send_message(int(target), f"🟢 *Admin reply:*\n{md(update.message.text or '')}", parse_mode=ParseMode.MARKDOWN)
        await update.message.reply_text("✅ Delivered.")
    except Exception as e:
        await update.message.reply_text(f"Failed to deliver: {e}")

# ------------- commands -------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u_tg = update.effective_user
    # ensure user in DB
    db = db_open()
    try:
        u = db.query(User).filter(User.telegram_id == str(u_tg.id)).one_or_none()
        if not u:
            u = User(
                telegram_id=str(u_tg.id),
                name=u_tg.full_name or "",
                username=u_tg.username or "",
                started_at=now_utc(),
                trial_until=now_utc() + timedelta(days=10),
                created_at=now_utc(),
                updated_at=now_utc(),
            )
            db.add(u)
            db.commit()
            db.refresh(u)
        else:
            changed = False
            if not getattr(u, "started_at", None):
                u.started_at = now_utc(); changed = True
            if u.name != (u_tg.full_name or ""):
                u.name = u_tg.full_name or ""; changed = True
            if u.username != (u_tg.username or ""):
                u.username = u_tg.username or ""; changed = True
            if changed:
                u.updated_at = now_utc()
                db.commit()
    finally:
        db.close()

    welcome = (
        "👋 *Hello!* This bot is online and ready.\n\n"
        "Use /selftest to check status."
    )
    if update.message:
        await update.message.reply_text(welcome, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu_kb())
    elif update.callback_query:
        await update.callback_query.message.reply_text(welcome, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu_kb())

async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Main menu:", reply_markup=main_menu_kb())

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(help_text(is_admin(update.effective_user.id)), parse_mode=ParseMode.MARKDOWN)

async def selftest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot is active and responding normally!", reply_markup=main_menu_kb())

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    db = db_open()
    try:
        users = db.query(User).order_by(User.created_at.desc()).limit(30).all()
        lines = ["*Users (latest 30)*"]
        for u in users:
            lines.append(f"• `{u.telegram_id}` @{u.username or '—'}")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
    finally:
        db.close()

async def grant_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = context.args or []
    if len(args) != 2:
        await update.message.reply_text("Usage: /grant <telegram_id> <days>")
        return
    tgt, days = args[0], int(args[1])
    db = db_open()
    try:
        u = db.query(User).filter(User.telegram_id == str(tgt)).one_or_none()
        if not u:
            await update.message.reply_text("User not found.")
            return
        base = u.access_until if (u.access_until and u.access_until > now_utc()) else now_utc()
        u.access_until = base + timedelta(days=days)
        u.updated_at = now_utc()
        db.commit()
        await update.message.reply_text(f"Granted until {u.access_until.strftime('%Y-%m-%d %H:%M UTC')}")
        try:
            await context.bot.send_message(int(tgt), f"✅ Your access has been extended until {u.access_until.strftime('%Y-%m-%d %H:%M UTC')}.")
        except Exception:
            pass
    finally:
        db.close()

async def feedsstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admin only.")
        return
    path = os.getenv("FEEDS_STATS_PATH", "feeds_stats.json")
    if not os.path.exists(path):
        await update.message.reply_text("No cycle stats yet.")
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        sent = data.get("sent_this_cycle", 0)
        dur = data.get("cycle_seconds", 0.0)
        feeds = data.get("feeds_counts", {})
        lines = [f"*Feeds:*  sent=`{sent}`  in `{dur:.1f}s`", ""]
        for k, v in feeds.items():
            lines.append(f"{k}={v.get('count',0)}" + (f"  ⚠️ {v.get('error')}" if v.get("error") else ""))
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await update.message.reply_text(f"Failed to read stats: {e}")

# ------------- text router (buttons + Start as text) -------------
async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.message.text or "").strip()

    # Αν στείλει "Start" σαν απλό text, τρέξε start
    if txt.lower() in ("start", "/start"):
        await start_cmd(update, context)
        return

    if is_admin(update.effective_user.id) and context.user_data.get("reply_target"):
        await admin_sends_reply(update, context)
        return

    low = txt.lower()
    if low == "keywords":
        await update.message.reply_text(
            "Send keywords separated by commas (supports English & Greek).",
            parse_mode=ParseMode.MARKDOWN
        )
        context.user_data["await_keywords"] = True
        return

    if context.user_data.pop("await_keywords", False):
        db = db_open()
        try:
            u = db.query(User).filter(User.telegram_id == str(update.effective_user.id)).one_or_none()
            if not u:
                await update.message.reply_text("Please tap /start first.")
                return
            parts = [p.strip() for p in txt.split(",") if p.strip()]
            uniq = []
            seen = set()
            for p in parts:
                k = p.lower()
                if k not in seen:
                    seen.add(k)
                    uniq.append(p)
            db.query(Keyword).filter(Keyword.user_id == u.id).delete()
            for k in uniq:
                db.add(Keyword(user_id=u.id, keyword=k, created_at=now_utc()))
            db.commit()
            await update.message.reply_text(f"✅ Saved {len(uniq)} keywords.", reply_markup=main_menu_kb())
        finally:
            db.close()
        return

    if low == "saved jobs":
        db = db_open()
        try:
            u = db.query(User).filter(User.telegram_id == str(update.effective_user.id)).one_or_none()
            if not u:
                await update.message.reply_text("Please tap /start first.")
                return
            rows = (
                db.query(SavedJob).filter(SavedJob.user_id == u.id)
                .order_by(SavedJob.created_at.desc()).limit(10).all()
            )
            if not rows:
                await update.message.reply_text("No saved jobs yet.")
                return
            parts = ["*Saved Jobs*"]
            for r in rows:
                j = db.query(Job).filter(Job.id == r.job_id).one_or_none()
                if not j:
                    continue
                budget = ""
                if j.budget_min is not None and j.budget_max is not None and j.budget_currency:
                    budget = f"{int(j.budget_min)}–{int(j.budget_max)} {j.budget_currency}"
                title = md(j.title or "")
                parts += [
                    f"\n*{title}*",
                    f"{md((j.description or '')[:400])}…",
                    f"Budget: `{budget or '—'}`",
                    f"Matched: `{j.matched_keyword or '—'}`",
                    f"[Original]({j.original_url or j.url})",
                    f"[Proposal]({j.proposal_url or j.url})",
                ]
            await update.message.reply_text("\n".join(parts), parse_mode=ParseMode.MARKDOWN)
        finally:
            db.close()
        return

    if low == "settings":
        db = db_open()
        try:
            u = db.query(User).filter(User.telegram_id == str(update.effective_user.id)).one_or_none()
            if not u:
                await update.message.reply_text("Please tap /start first.")
                return
            await update.message.reply_text(settings_text(u), parse_mode=ParseMode.MARKDOWN)
        finally:
            db.close()
        return

    if low == "help":
        await help_cmd(update, context)
        return

    if low == "contact":
        await update.message.reply_text("✍️ Please type your message for the admin. I'll forward it right away.")
        context.user_data["await_contact"] = True
        return

    if context.user_data.pop("await_contact", False):
        await route_user_message_to_admin(update, context)
        return

    await update.message.reply_text("Use the main buttons or /help.", reply_markup=main_menu_kb())

# ------------- callbacks -------------
async def button_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data or ""
    await q.answer()
    if data == "nav:menu":
        await q.message.reply_text("Main menu:", reply_markup=main_menu_kb())
        return
    if data.startswith("admin_reply:") or data.startswith("admin_decline:"):
        await handle_admin_reply_click(update, context)
        return

# ------------- error handler -------------
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    tb = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))
    print(f"[PTB ERROR]\n{tb}")
    if ADMIN_TG_ID:
        try:
            await context.bot.send_message(int(ADMIN_TG_ID), f"⚠️ Bot error:\n{tb[:3500]}")
        except Exception:
            pass

# ------------- FastAPI webhook -------------
app = FastAPI()

@app.on_event("startup")
async def _startup():
    # set webhook on startup (robust)
    if BOT_TOKEN and WEBHOOK_URL:
        try:
            application.bot.delete_webhook()
            application.bot.set_webhook = application.bot.set_webhook  # silence pyright
            await application.bot.delete_webhook()
            await application.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook/{WEBHOOK_SECRET}")
            print(f"[startup] Webhook set to {WEBHOOK_URL}/webhook/{WEBHOOK_SECRET}")
        except Exception as e:
            print("[startup] set_webhook error:", e)

@app.post(f"/webhook/{WEBHOOK_SECRET}")
async def tg_webhook(request: Request):
    try:
        data = await request.json()
        kind = (
            data.get("message", {}).get("text")
            or data.get("callback_query", {}).get("data")
            or "update"
        )
        print(f"[webhook] incoming: {kind}")
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        return JSONResponse({"ok": True})
    except Exception as e:
        print("[webhook] ERROR:", e)
        print(traceback.format_exc())
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

@app.get("/")
def root():
    return {"status": "ok"}

# ------------- build PTB app -------------
def build_application():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN missing")
    appb = ApplicationBuilder().token(BOT_TOKEN).build()

    appb.add_handler(CommandHandler("start", start_cmd))
    appb.add_handler(CommandHandler("menu", menu_cmd))
    appb.add_handler(CommandHandler("help", help_cmd))
    appb.add_handler(CommandHandler("selftest", selftest_cmd))
    appb.add_handler(CommandHandler("admin", admin_cmd))
    appb.add_handler(CommandHandler("grant", grant_cmd))
    appb.add_handler(CommandHandler("feedsstatus", feedsstatus_cmd))

    appb.add_handler(CallbackQueryHandler(button_cb))

    # Text (κουμπιά + "Start" ως free text)
    appb.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))

    appb.add_error_handler(on_error)
    return appb

application = build_application()

if __name__ == "__main__":
    uvicorn.run("bot:app", host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
