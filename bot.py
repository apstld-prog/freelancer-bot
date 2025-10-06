# bot.py
import os
import logging
from datetime import timedelta
from typing import List, Tuple, Optional

from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

from db import (
    get_session, init_db, now_utc,
    User, Keyword, Job, SavedJob, ContactThread
)

# ----------------------------------------------------------------------------
# Config & Logging
# ----------------------------------------------------------------------------
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("bot")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = str(os.getenv("TELEGRAM_ADMIN_ID", "") or "").strip()

AFFILIATE_FREELANCER_REF = os.getenv("AFFILIATE_FREELANCER_REF", "")  # e.g. apstld
AFFILIATE_FIVERR_BTA = os.getenv("AFFILIATE_FIVERR_BTA", "")          # e.g. 1146042

TRIAL_DAYS = int(os.getenv("TRIAL_DAYS", "10"))

# Email (optional, for contact flow copies)
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")  # where admin copies go

# ----------------------------------------------------------------------------
# Helpers (UI / formatting)
# ----------------------------------------------------------------------------

def esc(s: Optional[str]) -> str:
    """Simple HTML escape to keep Telegram happy."""
    if not s:
        return ""
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
    )

FEATURES_TEXT = (
    "<b>✨ Features</b>\n"
    "• Realtime job alerts (Freelancer API)\n"
    "• Affiliate-wrapped <b>Proposal</b> & <b>Original</b> links\n"
    "• Budget shown + USD conversion\n"
    "• ⭐ Keep / 🗑️ Delete buttons\n"
    "• 10-day free trial, extend via admin\n"
    "• Multi-keyword search (single/all modes)\n"
    "• Platforms by country (incl. GR boards)\n"
)

PLATFORMS_TEXT = (
    "• Global: <b>Freelancer.com</b> (affiliate links), PeoplePerHour, Malt, Workana, Guru, "
    "99designs, Toptal*, Codeable*, YunoJuno*, Worksome*, twago, freelancermap\n"
    "  (* referral/curated platforms)\n"
    "• Greece: JobFind.gr, Skywalker.gr, Kariera.gr\n"
)

def main_menu_kb(is_admin: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("➕ Add Keywords", callback_data="mm:addkw"),
            InlineKeyboardButton("⚙️ Settings", callback_data="mm:settings"),
        ],
        [
            InlineKeyboardButton("📖 Help", callback_data="mm:help"),
            InlineKeyboardButton("💾 Saved", callback_data="mm:saved:1"),
        ],
        [
            InlineKeyboardButton("📨 Contact", callback_data="mm:contact"),
        ],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton("👑 Admin", callback_data="mm:admin")])
    return InlineKeyboardMarkup(rows)

def welcome_text() -> str:
    return (
        "👋 <b>Welcome to Freelancer Alert Bot!</b>\n\n"
        f"🎁 You have a <b>{TRIAL_DAYS}-day free trial</b>.\n"
        "Automatically finds matching freelance jobs from top platforms and sends you instant alerts with affiliate-safe links.\n\n"
        "Use /help to see how it works."
    )

def settings_text(u: User) -> str:
    trial = (u.trial_until.isoformat(sep=' ', timespec='seconds') + " UTC") if u.trial_until else "None"
    lic = (u.access_until.isoformat(sep=' ', timespec='seconds') + " UTC") if u.access_until else "None"
    active = "✅" if u.is_active() else "❌"
    blocked = "❌" if u.is_blocked else "✅"
    kws = ", ".join(sorted([k.keyword for k in u.keywords])) or "(none)"
    start_ts = u.started_at.isoformat(sep=' ', timespec='seconds') + " UTC" if u.started_at else "—"
    return (
        "🛠️ <b>Your Settings</b>\n"
        f"• Keywords: {esc(kws)}\n"
        f"• Countries: {esc(u.countries or 'ALL')}\n"
        f"• Proposal template: {esc(u.proposal_template or '(none)')}\n\n"
        f"🟢 Start date: {esc(start_ts)}\n"
        f"🟢 Trial ends: {esc(trial)}\n"
        f"🔑 License until: {esc(lic)}\n"
        f"✅ Active: {active}\n"
        f"⛔ Blocked: {blocked}\n\n"
        "🗂️ <b>Platforms monitored:</b>\n" + PLATFORMS_TEXT +
        "\nFor extension, contact the admin."
    )

HELP_TEXT_PUBLIC = (
    "🧭 <b>Help / How it works</b>\n\n"
    "1️⃣ Add keywords with <code>/addkeyword python, telegram</code> (comma-separated, English or Greek).\n"
    "2️⃣ Set your countries with <code>/setcountry US,UK</code> (or <code>ALL</code>).\n"
    "3️⃣ Save a proposal template with <code>/setproposal &lt;text&gt;</code>.\n"
    "   Placeholders: {jobtitle}, {experience}, {stack}, {availability}, {step1}, {step2}, {step3}, {budgettime}, {portfolio}, {name}\n"
    "4️⃣ When a job arrives you can:\n"
    "   ⭐ Keep it\n"
    "   🗑️ Delete it\n"
    "   📦 Proposal → direct affiliate link to job\n"
    "   🔗 Original → same affiliate-wrapped job link\n\n"
    "➤ Use <code>/mysettings</code> anytime to check your filters and proposal.\n"
    "➤ <code>/selftest</code> for a test job.\n"
    "➤ <code>/platforms CC</code> to see platforms by country (e.g., <code>/platforms GR</code>).\n\n"
    "🗂️ <b>Platforms monitored:</b>\n" + PLATFORMS_TEXT
)

HELP_TEXT_ADMIN_SUFFIX = (
    "\n\n👑 <b>Admin commands</b>\n"
    "• <code>/users</code> – list users\n"
    "• <code>/grant &lt;telegram_id&gt; &lt;days&gt;</code> – extend license\n"
    "• <code>/block &lt;telegram_id&gt;</code> / <code>/unblock &lt;telegram_id&gt;</code>\n"
    "• <code>/broadcast &lt;text&gt;</code> – send message to all active\n"
    "• <code>/feedsstatus</code> – show active feed toggles\n"
)

# ----------------------------------------------------------------------------
# Application
# ----------------------------------------------------------------------------

def build_application() -> Application:
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # core
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))
    app.add_handler(CommandHandler("whoami", whoami_cmd))

    # keywords / settings
    app.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app.add_handler(CommandHandler("delkeyword", delkeyword_cmd))
    app.add_handler(CommandHandler("clearkeywords", clearkeywords_cmd))
    app.add_handler(CommandHandler("keywords", keywords_cmd))
    app.add_handler(CommandHandler("setcountry", setcountry_cmd))
    app.add_handler(CommandHandler("setproposal", setproposal_cmd))
    app.add_handler(CommandHandler("platforms", platforms_cmd))
    app.add_handler(CommandHandler("selftest", selftest_cmd))

    # admin
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CommandHandler("grant", grant_cmd))
    app.add_handler(CommandHandler("block", block_cmd))
    app.add_handler(CommandHandler("unblock", unblock_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("feedsstatus", feedsstatus_cmd))

    # callbacks + contact flow
    app.add_handler(CallbackQueryHandler(button_cb))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), text_message_router))

    log.info("PTB Application initialized (webhook mode expected).")
    return app

# ----------------------------------------------------------------------------
# Runtime helpers
# ----------------------------------------------------------------------------

def is_admin(update: Update) -> bool:
    return bool(ADMIN_ID) and str(update.effective_user.id) == ADMIN_ID

def parse_keywords_arg(text: str) -> List[str]:
    raw = text.strip()
    for ch in ["\n", ";", "|"]:
        raw = raw.replace(ch, ",")
    parts = [p.strip() for p in raw.split(",")]
    kws = []
    for p in parts:
        if not p:
            continue
        # allow greek/english; split on whitespace if user forgot commas
        if " " in p and "," not in p:
            kws.extend([x for x in p.split(" ") if x])
        else:
            kws.append(p)
    out, seen = [], set()
    for k in kws:
        kk = k.strip().lower()
        if kk and kk not in seen:
            seen.add(kk)
            out.append(kk)
    return out[:50]

async def ensure_user(ctx: ContextTypes.DEFAULT_TYPE, tg_id: str, name: str, username: str) -> User:
    with get_session() as db:
        u = db.query(User).filter(User.telegram_id == str(tg_id)).one_or_none()
        if not u:
            u = User(
                telegram_id=str(tg_id),
                name=name or "",
                username=username or "",
                started_at=now_utc(),
                trial_until=now_utc() + timedelta(days=TRIAL_DAYS)
            )
            db.add(u); db.commit()
        else:
            changed = False
            if name and u.name != name:
                u.name = name; changed = True
            if username and u.username != username:
                u.username = username; changed = True
            if changed:
                db.commit()
        return u

def affiliate_wrap(source: str, url: str) -> Tuple[str, str]:
    # Keep both Proposal/Original affiliate-wrapped when possible
    if source == "freelancer" and AFFILIATE_FREELANCER_REF:
        if "referrer=" not in url and "ref=" not in url:
            sep = "&" if "?" in url else "?"
            url_aff = f"{url}{sep}referrer={AFFILIATE_FREELANCER_REF}"
            return url_aff, url_aff
    if source == "fiverr" and AFFILIATE_FIVERR_BTA:
        # already fully wrapped by the worker when building links
        return url, url
    return url, url

# ----------------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------------

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _ = await ensure_user(context, str(update.effective_user.id), update.effective_user.full_name, update.effective_user.username)
    await update.effective_chat.send_message(
        welcome_text(), reply_markup=main_menu_kb(is_admin(update)), parse_mode="HTML"
    )
    await update.effective_chat.send_message(FEATURES_TEXT, parse_mode="HTML")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = HELP_TEXT_PUBLIC + (HELP_TEXT_ADMIN_SUFFIX if is_admin(update) else "")
    await update.effective_chat.send_message(text, parse_mode="HTML")

async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as db:
        u = db.query(User).filter(User.telegram_id == str(update.effective_user.id)).one()
        await update.effective_chat.send_message(settings_text(u), parse_mode="HTML")

async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    txt = (
        f"🆔 Your Telegram ID: <code>{u.id}</code>\n"
        f"👤 Name: {esc(u.full_name)}\n"
        f"🔗 Username: @{esc(u.username or '(none)')}\n\n"
        + ("👑 You are <b>admin</b>." if is_admin(update) else "👤 You are a regular user.")
    )
    await update.effective_chat.send_message(txt, parse_mode="HTML")

async def addkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.effective_chat.send_message("Usage: /addkeyword <kw1, kw2, ...>")
        return
    kws = parse_keywords_arg(" ".join(context.args))
    with get_session() as db:
        u = db.query(User).filter(User.telegram_id == str(update.effective_user.id)).one()
        added = 0
        for k in kws:
            if not db.query(Keyword).filter(Keyword.user_id == u.id, Keyword.keyword == k).one_or_none():
                db.add(Keyword(user_id=u.id, keyword=k)); added += 1
        db.commit()
        # refresh list from DB to reflect new rows
        u = db.query(User).filter(User.id == u.id).one()
        lst = ", ".join(sorted([k.keyword for k in u.keywords])) or "(none)"
        await update.effective_chat.send_message(f"Added {added} keywords.\nYour keywords: {esc(lst)}", parse_mode="HTML")

async def delkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.effective_chat.send_message("Usage: /delkeyword <kw>")
        return
    kw = " ".join(context.args).strip().lower()
    with get_session() as db:
        u = db.query(User).filter(User.telegram_id == str(update.effective_user.id)).one()
        row = db.query(Keyword).filter(Keyword.user_id == u.id, Keyword.keyword == kw).one_or_none()
        if row:
            db.delete(row); db.commit()
            await update.effective_chat.send_message(f"Removed keyword: {esc(kw)}", parse_mode="HTML")
        else:
            await update.effective_chat.send_message("Not found.")

async def clearkeywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as db:
        u = db.query(User).filter(User.telegram_id == str(update.effective_user.id)).one()
        for r in list(u.keywords):
            db.delete(r)
        db.commit()
        await update.effective_chat.send_message("All keywords cleared.")

async def keywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as db:
        u = db.query(User).filter(User.telegram_id == str(update.effective_user.id)).one()
        lst = ", ".join(sorted([k.keyword for k in u.keywords])) or "(none)"
        await update.effective_chat.send_message(f"Your keywords: {esc(lst)}", parse_mode="HTML")

async def setcountry_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = " ".join(context.args) if context.args else "ALL"
    with get_session() as db:
        u = db.query(User).filter(User.telegram_id == str(update.effective_user.id)).one()
        u.countries = val or "ALL"; db.commit()
        await update.effective_chat.send_message(f"Countries set to: {esc(u.countries)}", parse_mode="HTML")

async def setproposal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.effective_message.text.partition(" ")[2]
    with get_session() as db:
        u = db.query(User).filter(User.telegram_id == str(update.effective_user.id)).one()
        u.proposal_template = text.strip() if text else None
        db.commit()
        await update.effective_chat.send_message("Proposal template saved.")

async def platforms_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cc = (context.args[0].upper() if context.args else "ALL")
    if cc == "GR":
        txt = "🇬🇷 <b>Greece</b>: JobFind.gr, Skywalker.gr, Kariera.gr"
    else:
        txt = "🌍 <b>Global</b>: Freelancer.com, PeoplePerHour, Malt, Workana, Guru, 99designs, Toptal*, Codeable*, YunoJuno*, Worksome*, twago, freelancermap"
    await update.effective_chat.send_message(txt, parse_mode="HTML")

async def selftest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(
        "🧪 <b>[TEST] Example job card</b>\n\n"
        "<b>Source:</b> Freelancer\n<b>Type:</b> Fixed\n<b>Budget:</b> 100–300 USD\n<b>~ $100.00–$300.00 USD</b>\n<b>Bids:</b> 12\n<b>Posted:</b> 0s ago\n\n"
        "Keyword matched: TEST",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 Proposal", url="https://www.freelancer.com/"),
             InlineKeyboardButton("🔗 Original", url="https://www.freelancer.com/")],
            [InlineKeyboardButton("⭐ Keep", callback_data="keep:test"),
             InlineKeyboardButton("🗑️ Delete", callback_data="del:test")]
        ])
    )

# ----------------------------------------------------------------------------
# Admin
# ----------------------------------------------------------------------------

async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    with get_session() as db:
        users = db.query(User).order_by(User.created_at.desc()).limit(200).all()
        lines = []
        for u in users:
            lines.append(
                f"• <code>{u.telegram_id}</code> {esc(u.name or '')} @{esc(u.username or '')}  active={'yes' if u.is_active() else 'no'}"
            )
        await update.effective_chat.send_message("👥 <b>Users</b>\n" + "\n".join(lines), parse_mode="HTML")

async def grant_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    if len(context.args) < 2:
        await update.effective_chat.send_message("Usage: /grant <telegram_id> <days>")
        return
    tg_id = context.args[0]
    days = int(context.args[1])
    with get_session() as db:
        u = db.query(User).filter(User.telegram_id == str(tg_id)).one_or_none()
        if not u:
            await update.effective_chat.send_message("User not found.")
            return
        base = u.access_until if (u.access_until and u.access_until > now_utc()) else now_utc()
        u.access_until = base + timedelta(days=days)
        db.commit()
        await update.effective_chat.send_message(
            f"Granted until {u.access_until.isoformat(sep=' ', timespec='seconds')} UTC"
        )

async def block_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    if not context.args:
        await update.effective_chat.send_message("Usage: /block <telegram_id>")
        return
    with get_session() as db:
        u = db.query(User).filter(User.telegram_id == str(context.args[0])).one_or_none()
        if not u:
            await update.effective_chat.send_message("User not found.")
            return
        u.is_blocked = True; db.commit()
        await update.effective_chat.send_message("Blocked.")

async def unblock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    if not context.args:
        await update.effective_chat.send_message("Usage: /unblock <telegram_id>")
        return
    with get_session() as db:
        u = db.query(User).filter(User.telegram_id == str(context.args[0])).one_or_none()
        if not u:
            await update.effective_chat.send_message("User not found.")
            return
        u.is_blocked = False; db.commit()
        await update.effective_chat.send_message("Unblocked.")

async def feedsstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    flags = []
    for k in [
        "ENABLE_FREELANCER","ENABLE_PPH","ENABLE_KARIERA","ENABLE_JOBFIND",
        "ENABLE_TWAGO","ENABLE_FREELANCERMAP","ENABLE_YUNOJUNO","ENABLE_WORKSOME",
        "ENABLE_CODEABLE","ENABLE_GURU","ENABLE_99DESIGNS"
    ]:
        flags.append(f"{k}={os.getenv(k,'0')}")
    await update.effective_chat.send_message("Feeds:\n" + "\n".join(flags))

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    msg = update.message.text.partition(" ")[2]
    if not msg:
        await update.effective_chat.send_message("Usage: /broadcast <text>")
        return
    with get_session() as db:
        users = db.query(User).all()
    sent = 0
    for u in users:
        try:
            await context.bot.send_message(chat_id=int(u.telegram_id), text=msg)
            sent += 1
        except Exception:
            pass
    await update.effective_chat.send_message(f"Broadcast sent to {sent} users.")

# ----------------------------------------------------------------------------
# SMTP mail (optional)
# ----------------------------------------------------------------------------

def send_mail_copy(subject: str, body: str) -> None:
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS and ADMIN_EMAIL):
        return
    try:
        import smtplib
        from email.message import EmailMessage
        m = EmailMessage()
        m["From"] = SMTP_USER
        m["To"] = ADMIN_EMAIL
        m["Subject"] = subject
        m.set_content(body)
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(m)
    except Exception as e:
        log.warning("Email send failed: %s", e)

# ----------------------------------------------------------------------------
# Buttons / Contact & Replies
# ----------------------------------------------------------------------------

async def button_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""

    if data == "mm:addkw":
        await q.message.reply_text("Send <code>/addkeyword kw1, kw2, kw3</code>", parse_mode="HTML")
        return

    if data == "mm:settings":
        with get_session() as db:
            u = db.query(User).filter(User.telegram_id == str(update.effective_user.id)).one()
            await q.message.reply_text(settings_text(u), parse_mode="HTML")
        return

    if data == "mm:help":
        text = HELP_TEXT_PUBLIC + (HELP_TEXT_ADMIN_SUFFIX if is_admin(update) else "")
        await q.message.reply_text(text, parse_mode="HTML")
        return

    if data.startswith("mm:saved:"):
        page = int(data.split(":")[2])
        await show_saved_jobs(update, context, page)
        return

    if data == "mm:contact":
        with get_session() as db:
            u = db.query(User).filter(User.telegram_id == str(update.effective_user.id)).one()
            th = ContactThread(user_id=u.id, is_open=True)
            db.add(th); db.commit()
        await q.message.reply_text("✍️ Please type your message for the admin. I'll forward it right away.")
        return

    if data == "mm:admin":
        if not is_admin(update):
            await q.message.reply_text("Admins only.")
            return
        await q.message.reply_text(
            "Admin panel: use the commands in /help (admin section).",
            parse_mode="HTML"
        )
        return

    # Saved jobs buttons
    if data.startswith("saved:open:"):
        job_key = data.split(":")[2]
        await show_job_card(update, context, job_key)
        return

    if data.startswith("saved:del:"):
        job_key = data.split(":")[2]
        with get_session() as db:
            u = db.query(User).filter(User.telegram_id == str(update.effective_user.id)).one()
            # try int, else fallback to string (DB type differences safe-guard)
            try:
                jid = int(job_key)
                row = db.query(SavedJob).filter(SavedJob.user_id == u.id, SavedJob.job_id == jid).one_or_none()
            except ValueError:
                row = db.query(SavedJob).filter(SavedJob.user_id == u.id, SavedJob.job_id == job_key).one_or_none()
            if row:
                db.delete(row); db.commit()
                await q.message.reply_text("Deleted from saved.")
        return

    # Keep/Delete on job cards (from worker)
    if data.startswith("keep:"):
        job_key = data.split(":", 1)[1]
        with get_session() as db:
            u = db.query(User).filter(User.telegram_id == str(update.effective_user.id)).one()
            # persist saved
            try:
                jid = int(job_key)
                job = db.query(Job).filter(Job.id == jid).one_or_none()
            except ValueError:
                job = db.query(Job).filter(Job.id == job_key).one_or_none()
            if job:
                if not db.query(SavedJob).filter(SavedJob.user_id == u.id, SavedJob.job_id == job.id).one_or_none():
                    db.add(SavedJob(user_id=u.id, job_id=job.id))
                    db.commit()
                await q.message.reply_text("⭐ Saved.")
            else:
                await q.message.reply_text("Not found.")
        return

    if data.startswith("del:"):
        try:
            await q.message.delete()
        except Exception:
            pass
        return

    # Admin reply/decline on contact threads
    if data.startswith("admreply:"):
        if not is_admin(update):
            await q.message.reply_text("Admins only.")
            return
        target_tg = data.split(":", 1)[1]
        context.user_data["reply_to"] = str(target_tg)
        await q.message.reply_text(f"Reply mode enabled. Your next message will be sent to user <code>{esc(target_tg)}</code>.", parse_mode="HTML")
        return

    if data.startswith("admdecline:"):
        if not is_admin(update):
            await q.message.reply_text("Admins only.")
            return
        target_tg = data.split(":", 1)[1]
        try:
            await context.bot.send_message(chat_id=int(target_tg), text="🚫 Your message was declined by the admin.")
        except Exception:
            pass
        await q.message.reply_text("Declined.")
        return

async def show_saved_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int):
    with get_session() as db:
        u = db.query(User).filter(User.telegram_id == str(update.effective_user.id)).one()
        rows = (db.query(SavedJob)
                  .filter(SavedJob.user_id == u.id)
                  .order_by(SavedJob.created_at.desc())
                  .limit(20).all())
        if not rows:
            await update.effective_chat.send_message("No saved jobs yet.")
            return
        for sj in rows:
            job = db.query(Job).filter(Job.id == sj.job_id).one_or_none()
            if not job:
                continue
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Open", callback_data=f"saved:open:{job.id}"),
                 InlineKeyboardButton("🗑️ Delete", callback_data=f"saved:del:{job.id}")]
            ])
            await update.effective_chat.send_message(
                f"• {esc(job.source)} — {esc(job.title)}", reply_markup=kb, parse_mode="HTML"
            )

async def show_job_card(update: Update, context: ContextTypes.DEFAULT_TYPE, job_key):
    with get_session() as db:
        try:
            jid = int(job_key)
            job = db.query(Job).filter(Job.id == jid).one()
        except ValueError:
            job = db.query(Job).filter(Job.id == job_key).one()
        prop = job.proposal_url or job.url
        orig = job.original_url or job.url
        prop, orig = affiliate_wrap(job.source or "", prop), affiliate_wrap(job.source or "", orig)
        # affiliate_wrap returns (p,o) but we passed single; fix:
        prop_url = prop[0] if isinstance(prop, tuple) else prop
        orig_url = orig[1] if isinstance(orig, tuple) else orig

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 Proposal", url=prop_url),
             InlineKeyboardButton("🔗 Original", url=orig_url)]
        ])
        btxt = ""
        if (job.budget_min is not None) or (job.budget_max is not None):
            cur = job.budget_currency or ""
            rng = f"{job.budget_min or ''}–{job.budget_max or ''} {cur}".strip("– ").strip()
            btxt = f"\n💲 Budget: {esc(rng)}"
        desc = (job.description or "")
        desc_short = (desc[:400] + "…") if len(desc) > 400 else desc
        await update.effective_chat.send_message(
            f"<b>{esc(job.title)}</b>\nSource: {esc(job.source)}{btxt}\n\n{esc(desc_short)}",
            parse_mode="HTML", reply_markup=kb
        )

# ----------------------------------------------------------------------------
# Text Router: contact flow + admin reply mode
# ----------------------------------------------------------------------------

async def text_message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # If admin is in reply mode, send the text to the selected user
    if is_admin(update) and context.user_data.get("reply_to"):
        target = context.user_data.pop("reply_to")
        txt = update.effective_message.text
        # forward to user
        try:
            await context.bot.send_message(chat_id=int(target), text=f"📨 <b>Admin reply:</b>\n{esc(txt)}", parse_mode="HTML")
        except Exception as e:
            await update.effective_chat.send_message(f"Send failed: {e}")
            return
        await update.effective_chat.send_message("✅ Sent.")
        # email copy
        send_mail_copy(subject=f"Admin reply to {target}", body=txt)
        return

    # Otherwise, treat as user contact message
    with get_session() as db:
        u = await ensure_user(context, str(update.effective_user.id), update.effective_user.full_name, update.effective_user.username)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("↩️ Reply", callback_data=f"admreply:{u.telegram_id}"),
             InlineKeyboardButton("🚫 Decline", callback_data=f"admdecline:{u.telegram_id}")]
        ])
        txt = (
            "📩 <b>Message from user</b>\n"
            f"• ID: <code>{u.telegram_id}</code>\n"
            f"• Name: {esc(u.name)}\n"
            f"• Username: @{esc(u.username or '(none)')}\n\n"
            f"{esc(update.effective_message.text)}"
        )
    if ADMIN_ID:
        await context.bot.send_message(chat_id=int(ADMIN_ID), text=txt, parse_mode="HTML", reply_markup=kb)
    await update.effective_chat.send_message("✅ Sent to the admin. You’ll receive a reply here.")
    # email copy to admin mailbox
    send_mail_copy(subject=f"Message from user {u.telegram_id}", body=update.effective_message.text)

# ----------------------------------------------------------------------------
# Entrypoint for local run
# ----------------------------------------------------------------------------

if __name__ == "__main__":
    app = build_application()
    app.run_polling(drop_pending_updates=True)
