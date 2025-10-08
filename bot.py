# bot.py
# -*- coding: utf-8 -*-
# ==========================================================
# UI_LOCKED: Message layout & buttons must match previous spec
# ==========================================================
import os
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from fastapi import FastAPI
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from db import (
    SessionLocal,
    ensure_schema,
    User,
    Keyword,
    Job,
    JobSent,
)

# ------------------ Config & Globals ------------------

UTC = timezone.utc
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(level=LOG_LEVEL)
log = logging.getLogger("bot")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_TELEGRAM_ID = os.getenv("ADMIN_TELEGRAM_ID", "").strip()  # string id is fine

WELCOME_CARD = (
    "👋 <b>Welcome to Freelancer Alert Bot!</b>\n\n"
    "🎁 <b>You have a 10-day free trial.</b>\n"
    "Automatically finds matching freelance jobs from top platforms and sends you instant alerts.\n\n"
    "Use <code>/help</code> to see how it works."
)

HELP_CARD = (
    "🧭 <b>Help / How it works</b>\n\n"
    "1️⃣ Add keywords with <code>/addkeyword python, telegram</code> (comma-separated, English or Greek).\n"
    "2️⃣ Set your countries with <code>/setcountry US,UK</code> (or <code>ALL</code>).\n"
    "3️⃣ Save a proposal template with <code>/setproposal &lt;text&gt;</code> —\n"
    "   Placeholders: {jobtitle}, {experience}, {stack}, {availability}, {step1}, {step2}, {step3}, {budgettime}, {portfolio}, {name}.\n"
    "4️⃣ When a job arrives you can:\n"
    "   ⭐ Keep it\n"
    "   🗑️ Delete it\n"
    "   📨 <b>Proposal</b> → direct link to job\n"
    "   🔗 <b>Original</b> → same wrapped job link\n\n"
    "▶ Use <code>/mysettings</code> anytime to check your filters and proposal.\n"
    "▶ <code>/selftest</code> for a test job.\n"
    "▶ <code>/platforms CC</code> to see platforms by country (e.g., <code>/platforms GR</code>).\n\n"
    "🗂 Platforms monitored:\n"
    "Global: <a href='https://www.freelancer.com'>Freelancer.com</a>, PeoplePerHour, Malt, Workana, Guru, 99designs, Toptal*, Codeable*, YunoJuno*, Worksome*, twago, freelancermap (*referral/curated)\n"
    "Greece: JobFind.gr, Skywalker.gr, Kariera.gr\n\n"
    "👑 <b>Admin commands</b>\n"
    "<code>/users</code> — list users\n"
    "<code>/grant &lt;telegram_id&gt; &lt;days&gt;</code> — extend license\n"
    "<code>/block &lt;telegram_id&gt;</code> / <code>/unblock &lt;telegram_id&gt;</code>\n"
    "<code>/feedstatus</code> — show active feed toggles / stats\n"
)

MENU_ROWS = [
    [
        InlineKeyboardButton("+ Add Keywords", callback_data="act:addkw"),
        InlineKeyboardButton("⚙️ Settings", callback_data="act:settings"),
    ],
    [
        InlineKeyboardButton("🆘 Help", callback_data="act:help"),
        InlineKeyboardButton("💾 Saved", callback_data="act:saved"),
    ],
    [
        InlineKeyboardButton("📞 Contact", callback_data="act:contact"),
        InlineKeyboardButton("👑 Admin", callback_data="act:admin"),
    ],
]

REPLY_ROWS = [
    [
        InlineKeyboardButton("💬 Reply", callback_data="adm:reply"),
        InlineKeyboardButton("❌ Decline", callback_data="adm:decline"),
    ],
    [
        InlineKeyboardButton("+30d", callback_data="adm:grant:30"),
        InlineKeyboardButton("+90d", callback_data="adm:grant:90"),
    ],
    [
        InlineKeyboardButton("+180d", callback_data="adm:grant:180"),
        InlineKeyboardButton("+365d", callback_data="adm:grant:365"),
    ],
]

# ------------------ Helpers ------------------

def now_utc() -> datetime:
    return datetime.now(UTC)

def is_admin(update: Update) -> bool:
    uid = str(update.effective_user.id if update.effective_user else "")
    return ADMIN_TELEGRAM_ID and uid == ADMIN_TELEGRAM_ID

def get_or_create_user(db, tg_id: int) -> User:
    u = db.query(User).filter(User.telegram_id == str(tg_id)).one_or_none()
    if not u:
        u = User(
            telegram_id=str(tg_id),
            trial_start=now_utc(),
            trial_end=now_utc() + timedelta(days=10),
            is_blocked=False,
            created_at=now_utc(),
            updated_at=now_utc(),
        )
        db.add(u)
        db.commit()
        db.refresh(u)
    return u

def settings_card(u: User, keywords: List[str]) -> str:
    trial_start = getattr(u, "trial_start", None)
    trial_end = getattr(u, "trial_end", None)
    license_until = getattr(u, "license_until", None)

    # Expiration logic (license takes precedence)
    expires = license_until or trial_end
    days_left = ""
    if expires:
        days = max(0, (expires - now_utc()).days)
        days_left = f" (in {days} day(s))"

    lines = [
        "🛠 <b>Your Settings</b>",
        f"• Keywords: {', '.join(keywords) if keywords else '(none)'}",
        "• Countries: ALL",
        "• Proposal template: (none)",
        "",
        f"Trial start: {trial_start.isoformat() if trial_start else 'None'}",
        f"Trial ends: {trial_end.isoformat() if trial_end else 'None'}",
        f"License until: {license_until.isoformat() if license_until else 'None'}",
        f"Expires: {expires.isoformat() if expires else 'None'}{days_left}",
        f"Active: {'✅' if expires and expires >= now_utc() and not getattr(u, 'is_blocked', False) else '❌'}  Blocked: {'❌' if not getattr(u,'is_blocked',False) else '✅'}",
        "",
        "Platforms monitored:",
        "Freelancer.com, PeoplePerHour, Malt, Workana, Guru, 99designs, Toptal*, Codeable*, YunoJuno*, Worksome*, twago, freelancermap (*referral/curated)",
        "",
        "Greece: JobFind.gr, Skywalker.gr, Kariera.gr",
        "",
        "When your trial ends, please contact the admin to extend your access.",
    ]
    return "\n".join(lines)

async def send_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup(MENU_ROWS)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=WELCOME_CARD,
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
        disable_web_page_preview=True,
    )

# ------------------ Commands ------------------

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        get_or_create_user(db, update.effective_user.id)
    finally:
        db.close()
    await send_menu(update, context)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=HELP_CARD,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )

async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id if update.effective_user else "")
    role = "Admin" if ADMIN_TELEGRAM_ID and uid == ADMIN_TELEGRAM_ID else "User"
    text = f"🆔 Your ID: <a href='tg://user?id={uid}'>{uid}</a>\nRole: <b>{role}</b>"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

async def addkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add keywords (comma-separated)."""
    if not context.args:
        await update.message.reply_text("Usage: /addkeyword word1, word2, ...")
        return
    raw = " ".join(context.args)
    terms = [t.strip() for t in raw.split(",") if t.strip()]
    if not terms:
        await update.message.reply_text("No keywords detected.")
        return

    db = SessionLocal()
    try:
        u = get_or_create_user(db, update.effective_user.id)
        inserted = 0
        for t in terms:
            exists = db.query(Keyword).filter(Keyword.user_id == u.id, Keyword.term == t).one_or_none()
            if exists:
                continue
            # NOTE: do NOT pass created_at/updated_at here; DB handles defaults
            k = Keyword(user_id=u.id, term=t)
            db.add(k)
            inserted += 1
        db.commit()
        await update.message.reply_text(f"Added {inserted} keyword(s).")
    except Exception as e:
        db.rollback()
        log.exception("addkeyword failed")
        await update.message.reply_text(f"⚠️ Error while adding: {e}")
    finally:
        db.close()

async def keywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        u = get_or_create_user(db, update.effective_user.id)
        rows = db.query(Keyword).filter(Keyword.user_id == u.id).order_by(Keyword.id.asc()).all()
        if not rows:
            await update.message.reply_text("No keywords yet. Use /addkeyword word1, word2")
            return
        lines = [f"• [{k.id}] {k.term}" for k in rows]
        await update.message.reply_text("Your keywords:\n" + "\n".join(lines))
    finally:
        db.close()

async def delkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete by id or by exact term."""
    if not context.args:
        await update.message.reply_text("Usage: /delkeyword <id> or /delkeyword <term>")
        return
    arg = " ".join(context.args).strip()
    db = SessionLocal()
    try:
        u = get_or_create_user(db, update.effective_user.id)
        deleted = 0
        if arg.isdigit():
            q = db.query(Keyword).filter(Keyword.user_id == u.id, Keyword.id == int(arg))
            deleted = q.delete()
        else:
            q = db.query(Keyword).filter(Keyword.user_id == u.id, Keyword.term == arg)
            deleted = q.delete()
        db.commit()
        await update.message.reply_text(f"Deleted {deleted} keyword(s).")
    except Exception as e:
        db.rollback()
        await update.message.reply_text(f"⚠️ Error: {e}")
    finally:
        db.close()

async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        u = get_or_create_user(db, update.effective_user.id)
        kws = [r[0] for r in db.query(Keyword.term).filter(Keyword.user_id == u.id).all()]
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=settings_card(u, kws),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    finally:
        db.close()

async def saved_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show latest 10 saved jobs as full cards (same layout as alerts)."""
    db = SessionLocal()
    try:
        u = get_or_create_user(db, update.effective_user.id)
        qs = (
            db.query(Job)
            .join(JobSent, JobSent.job_id == Job.id)
            .filter(JobSent.user_id == u.id, JobSent.is_saved == True)
            .order_by(JobSent.created_at.desc())
            .limit(10)
            .all()
        )
        if not qs:
            await update.message.reply_text("No saved jobs yet.")
            return
        for j in qs:
            await send_job_card(context, update.effective_chat.id, j)
    finally:
        db.close()

async def feedstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Count JobSent per source in last 24h."""
    db = SessionLocal()
    try:
        since = now_utc() - timedelta(hours=24)
        rows = (
            db.query(Job.source, User.id)
            .join(JobSent, JobSent.job_id == Job.id)
            .join(User, User.id == JobSent.user_id)
            .filter(JobSent.created_at >= since)
            .all()
        )
        # Aggregate in Python to avoid raw SQL
        counts = {}
        for src, _ in rows:
            counts[src] = counts.get(src, 0) + 1
        if not counts:
            await update.message.reply_text("📊 Sent jobs by platform (last 24h)\n• (none)")
            return
        lines = ["📊 Sent jobs by platform (last 24h)"]
        for src, c in sorted(counts.items(), key=lambda x: x[0].lower()):
            lines.append(f"• {src}: {c}")
        await update.message.reply_text("\n".join(lines))
    finally:
        db.close()

# ------------------ Job cards (same style as worker) ------------------

def compose_message(job: Job) -> str:
    parts = [f"{job.title or 'Untitled'}"]
    if job.budget_min or job.budget_max:
        lo = job.budget_min or 0
        hi = job.budget_max or 0
        cur = job.budget_currency or ""
        if lo and hi:
            parts.append(f"🧾 Budget: {lo}–{hi} {cur}")
        else:
            parts.append(f"🧾 Budget: {lo or hi} {cur}")
    parts.append(f"📎 Source: {job.source or ''}")
    if getattr(job, "matched_keyword", None):
        parts.append(f"🔍 Match: <b><u>{job.matched_keyword}</u></b>")
    desc = (job.description or "").strip()
    if desc:
        if len(desc) > 220:
            desc = desc[:220].rstrip() + "…"
        parts.append(f"📝 {desc}")
    if job.posted_at:
        delta = now_utc() - job.posted_at
        mins = int(delta.total_seconds() // 60)
        if mins < 60:
            parts.append(f"⏱️ {mins}m ago")
        else:
            hours = mins // 60
            parts.append(f"⏱️ {hours}h ago")
    return "\n".join(parts)

def compose_keyboard(job: Job) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("📨 Proposal", url=job.proposal_url or job.url),
            InlineKeyboardButton("🔗 Original", url=job.original_url or job.url),
        ],
        [
            InlineKeyboardButton("⭐ Save", callback_data=f"job:save:{job.id}"),
            InlineKeyboardButton("🗑️ Delete", callback_data=f"job:delete:{job.id}"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)

async def send_job_card(context: ContextTypes.DEFAULT_TYPE, chat_id: int, job: Job):
    await context.bot.send_message(
        chat_id=chat_id,
        text=compose_message(job),
        reply_markup=compose_keyboard(job),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )

# ------------------ Callback handlers ------------------

async def menu_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle main menu buttons (callback)."""
    q = update.callback_query
    data = q.data if q else ""
    db = SessionLocal()
    try:
        if data == "act:addkw":
            await context.bot.send_message(chat_id=q.message.chat_id, text="Use /addkeyword word1, word2")
            await q.answer()
            return
        if data == "act:settings":
            u = get_or_create_user(db, q.from_user.id)
            kws = [r[0] for r in db.query(Keyword.term).filter(Keyword.user_id == u.id).all()]
            await context.bot.send_message(
                chat_id=q.message.chat_id,
                text=settings_card(u, kws),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            await q.answer()
            return
        if data == "act:help":
            await context.bot.send_message(chat_id=q.message.chat_id, text=HELP_CARD, parse_mode=ParseMode.HTML)
            await q.answer()
            return
        if data == "act:saved":
            # reuse /saved
            fake = Update(update.update_id, message=update.effective_message)
            fake.effective_message = update.effective_message
            await saved_cmd(fake, context)
            await q.answer()
            return
        if data == "act:contact":
            await context.bot.send_message(
                chat_id=q.message.chat_id,
                text="Send your message for the admin. I will forward it.",
            )
            # Mark user as "awaiting contact"
            u = get_or_create_user(db, q.from_user.id)
            u.awaiting_contact = True  # requires nullable column, harmless if missing
            u.updated_at = now_utc()
            try:
                db.commit()
            except Exception:
                db.rollback()
            await q.answer()
            return
        if data == "act:admin":
            await context.bot.send_message(
                chat_id=q.message.chat_id,
                text="Admin panel: use /users, /grant <id> <days>, /block <id>, /unblock <id>, /feedstatus.",
                disable_web_page_preview=True,
            )
            await q.answer()
            return
    finally:
        db.close()

async def job_buttons_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Save/Delete buttons under job cards."""
    q = update.callback_query
    data = (q.data or "").split(":")
    if len(data) < 3:
        await q.answer()
        return
    action, job_id_s = data[1], data[2]
    db = SessionLocal()
    try:
        u = get_or_create_user(db, q.from_user.id)
        job = db.query(Job).filter(Job.id == int(job_id_s)).one_or_none()
        if not job:
            await q.answer("Not found", show_alert=False)
            return
        js = db.query(JobSent).filter(JobSent.user_id == u.id, JobSent.job_id == job.id).one_or_none()
        if not js:
            js = JobSent(user_id=u.id, job_id=job.id, created_at=now_utc())
            db.add(js)
        if action == "save":
            js.is_saved = True
            db.commit()
            await q.answer("Saved")
        elif action == "delete":
            # mark as deleted and remove buttons from message
            js.is_deleted = True
            db.commit()
            try:
                await q.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
            await q.answer("Deleted")
        else:
            await q.answer()
    except Exception as e:
        db.rollback()
        log.warning("job_buttons_cb error: %s", e)
        await q.answer("Error")
    finally:
        db.close()

# ------------------ Contact flow ------------------

async def any_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """If user is in 'awaiting_contact', forward to admin with Reply/Decline + grant rows."""
    if not update.message or not update.effective_user:
        return
    db = SessionLocal()
    try:
        u = get_or_create_user(db, update.effective_user.id)
        awaiting = bool(getattr(u, "awaiting_contact", False))
        if not awaiting:
            return
        # reset awaiting
        u.awaiting_contact = False
        u.updated_at = now_utc()
        try:
            db.commit()
        except Exception:
            db.rollback()

        if not ADMIN_TELEGRAM_ID:
            await update.message.reply_text("Admin is not configured.")
            return

        text = update.message.text_html or update.message.text or "(no text)"
        header = (
            "📩 <b>New message from user</b>\n"
            f"ID: <a href='tg://user?id={u.telegram_id}'>{u.telegram_id}</a>\n\n"
            f"{text}"
        )
        await context.bot.send_message(
            chat_id=int(ADMIN_TELEGRAM_ID),
            text=header,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(REPLY_ROWS),
            disable_web_page_preview=True,
        )
        await update.message.reply_text("Your message was sent to the admin. You will receive a reply here.")
    finally:
        db.close()

async def admin_buttons_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin reply / decline / grant buttons."""
    if not is_admin(update):
        await update.callback_query.answer()
        return
    q = update.callback_query
    data = q.data or ""
    if data == "adm:reply":
        await q.answer()
        await context.bot.send_message(chat_id=q.message.chat_id, text="✍️ Type your reply for the user id shown above…")
        # Store last target in context.chat_data? Keep simple: parse from previous message
        return
    if data == "adm:decline":
        await q.answer("Declined")
        return
    if data.startswith("adm:grant:"):
        days = int(data.split(":")[2])
        # Extract user id from the admin card text (line with ID:)
        try:
            text = q.message.text or ""
            # naive parse
            import re
            m = re.search(r"ID:\s+(\d+)", text)
            if not m:
                await q.answer("User id not found")
                return
            target_id = m.group(1)
            db = SessionLocal()
            try:
                u = db.query(User).filter(User.telegram_id == str(target_id)).one_or_none()
                if not u:
                    await q.answer("User not found")
                    return
                base = u.license_until or u.trial_end or now_utc()
                u.license_until = (base if base > now_utc() else now_utc()) + timedelta(days=days)
                u.updated_at = now_utc()
                db.commit()
                await q.answer(f"Granted +{days}d")
                await context.bot.send_message(chat_id=int(target_id), text=f"✅ Your access has been extended by {days} days.")
            finally:
                db.close()
        except Exception as e:
            log.warning("grant error: %s", e)
            await q.answer("Error")
        return
    await q.answer()

# ------------------ Build application ------------------

def build_application() -> Application:
    ensure_schema()
    app_ = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands
    app_.add_handler(CommandHandler("start", start_cmd))
    app_.add_handler(CommandHandler("help", help_cmd))
    app_.add_handler(CommandHandler("whoami", whoami_cmd))
    app_.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app_.add_handler(CommandHandler("keywords", keywords_cmd))
    app_.add_handler(CommandHandler("delkeyword", delkeyword_cmd))
    app_.add_handler(CommandHandler("mysettings", mysettings_cmd))
    app_.add_handler(CommandHandler("saved", saved_cmd))
    app_.add_handler(CommandHandler("feedstatus", feedstatus_cmd))

    # Menu & job buttons
    app_.add_handler(CallbackQueryHandler(menu_action_cb, pattern=r"^act:"))
    app_.add_handler(CallbackQueryHandler(job_buttons_cb, pattern=r"^job:(save|delete):"))
    app_.add_handler(CallbackQueryHandler(admin_buttons_cb, pattern=r"^adm:"))

    # Catch user message for contact flow
    app_.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, any_message))

    log.info("Handlers & jobs registered.")
    return app_

# ------------------ FastAPI wrapper for webhook ------------------

app = FastAPI()
application: Optional[Application] = None

@app.on_event("startup")
async def on_startup():
    global application
    application = build_application()
    await application.initialize()
    await application.start()
    # webhook is set by server.py

@app.on_event("shutdown")
async def on_shutdown():
    if application:
        await application.stop()
        await application.shutdown()

