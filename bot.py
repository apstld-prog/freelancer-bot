import asyncio
import logging
import os
from datetime import timedelta

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    constants,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from db import get_session, now_utc, User, Keyword, Job, SavedJob
from feedsstatus_handler import register_feedsstatus_handler  # παραμένει όπως το έχουμε
from worker_stats_sidecar import read_last_cycle_stats  # για /feedsstatus αν θες νούμερα

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_TG_ID = os.getenv("ADMIN_TG_ID", "")  # π.χ. "5254014824"
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "hook-secret-777")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL")  # π.χ. https://freelancer-bot-xxx.onrender.com

# --------------------------
# Helpers
# --------------------------
def is_admin(telegram_id: str) -> bool:
    return ADMIN_TG_ID and str(telegram_id) == str(ADMIN_TG_ID)

def main_menu_keyboard(is_admin_user: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("➕ Add Keywords", callback_data="ui:addkw"),
            InlineKeyboardButton("⚙️ Settings", callback_data="ui:settings"),
        ],
        [
            InlineKeyboardButton("📖 Help", callback_data="ui:help"),
            InlineKeyboardButton("💾 Saved", callback_data="ui:saved:1"),
        ],
        [
            InlineKeyboardButton("📨 Contact", callback_data="ui:contact"),
        ],
    ]
    if is_admin_user:
        rows.append([InlineKeyboardButton("👑 Admin", callback_data="ui:admin")])
    return InlineKeyboardMarkup(rows)

def features_block() -> str:
    return (
        "✨ <b>Features</b>\n"
        "• Realtime job alerts (Freelancer API)\n"
        "• Affiliate-wrapped <b>Proposal</b> & <b>Original</b> links\n"
        "• Budget shown + USD conversion\n"
        "• ⭐ Keep / 🗑️ Delete buttons\n"
        "• 10-day free trial, extend via admin\n"
        "• Multi-keyword search (single/all modes)\n"
        "• Platforms by country (incl. GR boards)\n"
    )

def help_text() -> str:
    return (
        "🧭 <b>Help / How it works</b>\n"
        "1️⃣ Add keywords with <code>/addkeyword python, telegram</code> (comma-separated, English or Greek).\n"
        "2️⃣ Set your countries with <code>/setcountry US,UK</code> (or <code>ALL</code>).\n"
        "3️⃣ Save a proposal template with <code>/setproposal &lt;text&gt;</code>.\n"
        "   Placeholders: {jobtitle}, {experience}, {stack}, {availability}, {step1}, {step2}, {step3}, {budgettime}, {portfolio}, {name}\n"
        "4️⃣ When a job arrives you can:\n"
        "   ⭐ Keep it\n"
        "   🗑️ Delete it\n"
        "   📦 Proposal → direct affiliate link to job\n"
        "   🔗 Original → same affiliate-wrapped job link\n"
        "\n"
        "▶ Use <code>/mysettings</code> anytime to check your filters and proposal.\n"
        "▶ <code>/selftest</code> for a test job.\n"
        "▶ <code>/platforms CC</code> to see platforms by country (e.g., <code>/platforms GR</code>).\n"
        "\n"
        "📋 <b>Platforms monitored</b>:\n"
        "• Global: <a href='https://www.freelancer.com/'>Freelancer.com</a> (affiliate links), PeoplePerHour, Malt,\n"
        "  Workana, Guru, 99designs, Toptal*, Codeable*, YunoJuno*, Worksome*, twago, freelancermap\n"
        "  (* referral/curated platforms)\n"
        "• Greece: <a href='https://www.jobfind.gr/'>JobFind.gr</a>, <a href='https://www.skywalker.gr/'>Skywalker.gr</a>, <a href='https://www.kariera.gr/'>Kariera.gr</a>\n"
        "\n"
        "👑 <b>Admin commands</b>\n"
        "/users — list users\n"
        "/grant &lt;telegram_id&gt; &lt;days&gt; — extend license\n"
        "/block &lt;telegram_id&gt; / /unblock &lt;telegram_id&gt;\n"
        "/broadcast &lt;text&gt; — send message to all active\n"
        "/feedsstatus — show active feed toggles\n"
    )

def settings_text(u: User) -> str:
    started = u.started_at.isoformat() if u.started_at else "—"
    trial = u.trial_until.isoformat() + " UTC" if u.trial_until else "—"
    lic = u.access_until.isoformat() + " UTC" if u.access_until else "None"
    kws = ", ".join([k.keyword for k in (u.keywords or [])]) or "(none)"
    countries = u.countries or "ALL"
    return (
        "🛠 <b>Your Settings</b>\n"
        f"• <b>Keywords</b>: {kws}\n"
        f"• <b>Countries</b>: {countries}\n"
        f"• <b>Proposal template</b>: {(u.proposal_template or '(none)')}\n"
        "\n"
        f"🟢 <b>Start date</b>: {started}\n"
        f"🕒 <b>Trial ends</b>: {trial}\n"
        f"🧾 <b>License until</b>: {lic}\n"
        f"✅ <b>Active</b>: {'✅' if not u.is_blocked else '❌'}\n"
        f"⛔ <b>Blocked</b>: {'✅' if u.is_blocked else '❌'}\n"
        "\n"
        "🗺 <b>Platforms monitored</b>:\n"
        "• Global: <a href='https://www.freelancer.com/'>Freelancer.com</a>, PeoplePerHour, Malt, Workana, Guru, 99designs,\n"
        "  Toptal*, Codeable*, YunoJuno*, Worksome*, twago, freelancermap\n"
        "• Greece: <a href='https://www.jobfind.gr/'>JobFind.gr</a>, <a href='https://www.skywalker.gr/'>Skywalker.gr</a>, <a href='https://www.kariera.gr/'>Kariera.gr</a>\n"
        "\nFor extension, contact the admin."
    )

def job_keyboard(job: Job) -> InlineKeyboardMarkup:
    jid = f"{job.source}-{job.source_id}"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📦 Proposal", url=(job.proposal_url or job.url)),
            InlineKeyboardButton("🔗 Original", url=(job.original_url or job.url)),
        ],
        [
            InlineKeyboardButton("⭐ Keep", callback_data=f"job:keep:{jid}"),
            InlineKeyboardButton("🗑️ Delete", callback_data=f"job:delmsg:{jid}"),
        ],
    ])

def format_job_card(job: Job) -> str:
    # Ενιαίο layout όπως στο screenshot – HTML parsing ασφαλές
    budget_main = ""
    if job.budget_min is not None and job.budget_max is not None and job.budget_currency:
        budget_main = f"{int(job.budget_min)}–{int(job.budget_max)} {job.budget_currency}"
    bids = str(job.bids_count) if job.bids_count is not None else "—"
    posted = "recent" if not job.posted_at else "recent"  # κρατάμε ίδιο wording
    desc = (job.description or "").strip().replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    if len(desc) > 280:
        desc = desc[:277] + " …"
    matched = job.matched_keyword or ""
    return (
        f"<b>{job.title}</b>\n\n"
        f"<b>Source:</b> {job.source.capitalize()}\n"
        f"<b>Type:</b> {job.job_type.capitalize() if job.job_type else '—'}\n"
        f"<b>Budget:</b> {budget_main}\n"
        f"<b>Bids:</b> {bids}\n"
        f"<b>Posted:</b> {posted}\n\n"
        f"{desc}\n\n"
        f"<i>Matched:</i> {matched}"
    )

async def ensure_user(context: ContextTypes.DEFAULT_TYPE, tg_id: str, full_name: str, username: str|None) -> User:
    async with get_session() as db:
        u = db.query(User).filter(User.telegram_id == str(tg_id)).one_or_none()
        if not u:
            u = User(
                telegram_id=str(tg_id),
                name=full_name,
                username=username,
                started_at=now_utc(),
                trial_until=now_utc() + timedelta(days=10),
                is_blocked=False,
                countries="ALL",
            )
            db.add(u)
            db.commit()
        else:
            # keep fresh name/username
            changed = False
            if u.name != full_name:
                u.name = full_name; changed = True
            if u.username != username:
                u.username = username; changed = True
            if changed:
                db.commit()
        return u

# --------------------------
# Commands / UI
# --------------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = await ensure_user(context, str(update.effective_user.id), update.effective_user.full_name, update.effective_user.username)
    text = (
        f"👋 <b>Welcome to Freelancer Alert Bot!</b>\n\n"
        f"🎁 You have a <b>10-day free trial</b>.\n"
        "Automatically finds matching freelance jobs from top platforms and sends you instant alerts with affiliate-safe links.\n\n"
        "Use <code>/help</code> to see how it works."
    )
    await update.effective_chat.send_message(
        text=text,
        reply_markup=main_menu_keyboard(is_admin(u.telegram_id)),
        parse_mode=constants.ParseMode.HTML,
        disable_web_page_preview=True,
    )
    # Features in separate card (όπως στο παλιό στήσιμο)
    await update.effective_chat.send_message(
        text=features_block(),
        parse_mode=constants.ParseMode.HTML,
        disable_web_page_preview=True,
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(
        text=help_text(),
        parse_mode=constants.ParseMode.HTML,
        disable_web_page_preview=True,
    )

async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with get_session() as db:
        u = db.query(User).filter(User.telegram_id == str(update.effective_user.id)).one()
        await update.effective_chat.send_message(
            text=settings_text(u),
            parse_mode=constants.ParseMode.HTML,
            disable_web_page_preview=True,
        )

async def addkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /addkeyword word1, word2, word3")
        return
    raw = " ".join(context.args)
    # υποστήριξη κόμμα/κενό, αγγλικά/ελληνικά
    parts = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
    async with get_session() as db:
        u = db.query(User).filter(User.telegram_id == str(update.effective_user.id)).one()
        added = []
        for p in parts:
            exists = db.query(Keyword).filter(Keyword.user_id == u.id, Keyword.keyword == p).one_or_none()
            if not exists:
                db.add(Keyword(user_id=u.id, keyword=p, created_at=now_utc()))
                added.append(p)
        db.commit()
        allk = ", ".join([k.keyword for k in db.query(Keyword).filter(Keyword.user_id == u.id).all()])
    await update.message.reply_text(f"Added: {', '.join(added) or '(none)'}\nYour keywords: {allk}")

async def keywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with get_session() as db:
        u = db.query(User).filter(User.telegram_id == str(update.effective_user.id)).one()
        allk = ", ".join([k.keyword for k in (u.keywords or [])]) or "(none)"
    await update.message.reply_text(f"Your keywords: {allk}")

async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    uname = u.username or "(none)"
    await update.message.reply_text(f"ID: {u.id}\nName: {u.full_name}\nUsername: {uname}")

# --------------------------
# Callbacks (UI)
# --------------------------
async def button_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data or ""
    await q.answer()

    if data == "ui:addkw":
        await q.message.reply_text("Send: /addkeyword word1, word2, word3")
        return

    if data == "ui:help":
        await q.message.reply_text(help_text(), parse_mode=constants.ParseMode.HTML, disable_web_page_preview=True)
        return

    if data == "ui:settings":
        async with get_session() as db:
            u = db.query(User).filter(User.telegram_id == str(q.from_user.id)).one()
        await q.message.reply_text(settings_text(u), parse_mode=constants.ParseMode.HTML, disable_web_page_preview=True)
        return

    if data.startswith("ui:saved"):
        # δείξε λίστα saved (τίτλοι ως links) – παραμένουμε λιτό
        page = 1
        try:
            parts = data.split(":")
            if len(parts) == 3:
                page = max(1, int(parts[2]))
        except:
            page = 1
        page_size = 10
        async with get_session() as db:
            u = db.query(User).filter(User.telegram_id == str(q.from_user.id)).one()
            qs = db.query(SavedJob).filter(SavedJob.user_id == u.id).order_by(SavedJob.created_at.desc())
            total = qs.count()
            rows = qs.offset((page-1)*page_size).limit(page_size).all()
            if not rows:
                await q.message.reply_text("No saved jobs.")
                return
            text = "⭐ <b>Saved jobs</b>\n\n" + "\n".join(
                [f"• <a href='{r.job_url}'>{r.job_label}</a>" for r in rows]
            )
        kb_rows = []
        if page > 1:
            kb_rows.append(InlineKeyboardButton("◀ Prev", callback_data=f"ui:saved:{page-1}"))
        if page * page_size < total:
            kb_rows.append(InlineKeyboardButton("Next ▶", callback_data=f"ui:saved:{page+1}"))
        await q.message.reply_text(text, parse_mode=constants.ParseMode.HTML, reply_markup=InlineKeyboardMarkup([kb_rows]) if kb_rows else None, disable_web_page_preview=True)
        return

    if data == "ui:contact":
        await q.message.reply_text("✍️ Please type your message for the admin. I’ll forward it right away.")
        context.user_data["contact_mode"] = True
        return

    if data == "ui:admin":
        if not is_admin(q.from_user.id):
            await q.message.reply_text("Admin only.")
            return
        await q.message.reply_text("Admin panel: /feedsstatus")
        return

    # Job actions
    if data.startswith("job:keep:"):
        jid = data.split(":", 2)[2]
        src, sid = jid.split("-", 1)
        async with get_session() as db:
            u = db.query(User).filter(User.telegram_id == str(q.from_user.id)).one()
            job = db.query(Job).filter(Job.source == src, Job.source_id == sid).one_or_none()
            label = job.title if job else jid
            url = (job.original_url or job.url) if job else None
            db.add(SavedJob(user_id=u.id, job_source=src, job_source_id=sid, job_label=label, job_url=url, created_at=now_utc()))
            db.commit()
        await q.message.reply_text("✅ Saved.")
        return

    if data.startswith("job:delmsg:"):
        try:
            await q.message.delete()
        except Exception:
            pass
        return

# αποστολή μηνύματος admin μέσω reply του χρήστη
async def all_text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # contact relay
    if context.user_data.get("contact_mode"):
        context.user_data["contact_mode"] = False
        # forward to admin (TG + email αν έχεις SMTP)
        msg = f"📩 Message from user {update.effective_user.id} (@{update.effective_user.username or 'none'}):\n\n{update.message.text}"
        if ADMIN_TG_ID:
            try:
                await context.bot.send_message(chat_id=int(ADMIN_TG_ID), text=msg)
            except Exception as e:
                log.warning("Failed to forward to admin: %s", e)
        await update.message.reply_text("✅ Sent to admin. You’ll get a reply here.")
        return

# --------------------------
# Selftest (στέλνει test job με τα 4 κουμπιά)
# --------------------------
async def selftest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fake = Job(
        source="freelancer",
        source_id="TEST",
        title="[TEST] Example job card",
        description="Short description for test purposes.",
        url="https://www.freelancer.com/",
        original_url="https://www.freelancer.com/",
        proposal_url="https://www.freelancer.com/",
        budget_min=100, budget_max=300, budget_currency="USD",
        job_type="fixed",
        bids_count=12,
        matched_keyword="TEST",
    )
    await update.effective_chat.send_message(
        text=format_job_card(fake),
        reply_markup=job_keyboard(fake),
        parse_mode=constants.ParseMode.HTML,
        disable_web_page_preview=True,
    )

# --------------------------
# Build / Run
# --------------------------
def build_application() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))
    app.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app.add_handler(CommandHandler("keywords", keywords_cmd))
    app.add_handler(CommandHandler("whoami", whoami_cmd))
    app.add_handler(CommandHandler("selftest", selftest_cmd))

    app.add_handler(CallbackQueryHandler(button_cb))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, all_text_router))

    # κρατάμε το /feedsstatus που έβαλες
    register_feedsstatus_handler(app)

    log.info("PTB Application initialized (webhook mode expected).")
    return app

# Για uvicorn/ASGI server.py
app = None
if os.getenv("RUN_DIRECT") == "1":
    # dev run (polling)
    async def _main():
        application = build_application()
        await application.initialize()
        await application.start()
        log.info("Application started (polling).")
        await application.updater.start_polling()
        await asyncio.Event().wait()

    asyncio.run(_main())
else:
    # εξάγει το αντικείμενο για server.py (webhook)
    app = build_application()
