import os
import logging
from datetime import timedelta
from typing import List, Tuple

from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler,
    filters, ContextTypes
)

from db import (
    get_session, init_db, now_utc, User, Keyword, Job, SavedJob, ContactThread
)

# ----------------------------------------------------------------------------
# Config & Logging
# ----------------------------------------------------------------------------
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("bot")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = os.getenv("TELEGRAM_ADMIN_ID", "")
AFFILIATE_FREELANCER_REF = os.getenv("AFFILIATE_FREELANCER_REF", "")
AFFILIATE_FIVERR_BTA = os.getenv("AFFILIATE_FIVERR_BTA", "")

TRIAL_DAYS = int(os.getenv("TRIAL_DAYS", "10"))

# ----------------------------------------------------------------------------
# UI snippets
# ----------------------------------------------------------------------------

FEATURES_TEXT = (
    "✨ *Features*\n"
    "• Realtime job alerts (Freelancer API)\n"
    "• Affiliate-wrapped *Proposal* & *Original* links\n"
    "• Budget shown + USD conversion\n"
    "• ⭐ *Keep* / 🗑️ *Delete* buttons\n"
    "• 10-day free trial, extend via admin\n"
    "• Multi-keyword search (single/all modes)\n"
    "• Platforms by country (incl. GR boards)\n"
)

PLATFORMS_TEXT = (
    "• Global: *Freelancer.com* (affiliate links), PeoplePerHour, Malt, Workana, Guru, "
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
        ]
    ]
    if is_admin:
        rows.append([InlineKeyboardButton("👑 Admin", callback_data="mm:admin")])
    return InlineKeyboardMarkup(rows)

def welcome_text() -> str:
    return (
        "👋 *Welcome to Freelancer Alert Bot!*\n\n"
        f"🎁 You have a *{TRIAL_DAYS}-day free trial*.\n"
        "Automatically finds matching freelance jobs from top platforms and sends you instant alerts with affiliate-safe links.\n\n"
        "Use /help to see how it works."
    )

def settings_text(u: User) -> str:
    trial = u.trial_until.isoformat(sep=' ', timespec='seconds')+" UTC" if u.trial_until else "None"
    lic = u.access_until.isoformat(sep=' ', timespec='seconds')+" UTC" if u.access_until else "None"
    active = "✅" if u.is_active() else "❌"
    blocked = "❌" if u.is_blocked else "✅"
    kws = ", ".join(sorted([k.keyword for k in u.keywords])) or "(none)"
    return (
        "🛠️ *Your Settings*\n"
        f"• Keywords: {kws}\n"
        f"• Countries: {u.countries}\n"
        f"• Proposal template: {(u.proposal_template or '(none)')}\n\n"
        f"🟢 Start date: {u.started_at.isoformat(sep=' ', timespec='seconds')} UTC\n"
        f"🟢 Trial ends: {trial}\n"
        f"🔑 License until: {lic}\n"
        f"✅ Active: {active}\n"
        f"⛔ Blocked: {blocked}\n\n"
        "🗂️ *Platforms monitored:*\n" + PLATFORMS_TEXT +
        "\nFor extension, contact the admin."
    )

HELP_TEXT_PUBLIC = (
    "🧭 *Help / How it works*\n\n"
    "1️⃣ Add keywords with `/addkeyword python, telegram` (comma-separated, English or Greek).\n"
    "2️⃣ Set your countries with `/setcountry US,UK` (or `ALL`).\n"
    "3️⃣ Save a proposal template with `/setproposal <text>`.\n"
    "   Placeholders: {jobtitle}, {experience}, {stack}, {availability}, {step1}, {step2}, {step3}, {budgettime}, {portfolio}, {name}\n"
    "4️⃣ When a job arrives you can:\n"
    "   ⭐ Keep it\n"
    "   🗑️ Delete it\n"
    "   📦 Proposal → direct affiliate link to job\n"
    "   🔗 Original → same affiliate-wrapped job link\n\n"
    "➤ Use `/mysettings` anytime to check your filters and proposal.\n"
    "➤ `/selftest` for a test job.\n"
    "➤ `/platforms CC` to see platforms by country (e.g., `/platforms GR`).\n\n"
    "🗂️ *Platforms monitored:*\n" + PLATFORMS_TEXT
)

HELP_TEXT_ADMIN_SUFFIX = (
    "\n\n👑 *Admin commands*\n"
    "• `/users` – list users\n"
    "• `/grant <telegram_id> <days>` – extend license\n"
    "• `/block <telegram_id>` / `/unblock <telegram_id>`\n"
    "• `/broadcast <text>` – send message to all active\n"
    "• `/feedsstatus` – show active feed toggles\n"
)

# ----------------------------------------------------------------------------
# Application
# ----------------------------------------------------------------------------

def build_application() -> Application:
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))
    app.add_handler(CommandHandler("whoami", whoami_cmd))

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

    app.add_handler(CallbackQueryHandler(button_cb))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), contact_flow_message))

    log.info("PTB Application initialized (webhook mode expected).")
    return app

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def is_admin(update: Update) -> bool:
    return ADMIN_ID and str(update.effective_user.id) == str(ADMIN_ID)

def parse_keywords_arg(text: str) -> List[str]:
    raw = text.strip()
    for ch in ["\n", ";", "|"]:
        raw = raw.replace(ch, ",")
    parts = [p.strip() for p in raw.split(",")]
    kws = []
    for p in parts:
        if not p:
            continue
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
    db = get_session()
    try:
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
    finally:
        db.close()

def affiliate_wrap(source: str, url: str) -> Tuple[str, str]:
    if source == "freelancer" and AFFILIATE_FREELANCER_REF:
        if "referrer=" not in url and "ref=" not in url:
            sep = "&" if "?" in url else "?"
            url_aff = f"{url}{sep}referrer={AFFILIATE_FREELANCER_REF}"
            return url_aff, url_aff
    if source == "fiverr" and AFFILIATE_FIVERR_BTA:
        return url, url
    return url, url

# ----------------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------------

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _ = await ensure_user(context, str(update.effective_user.id), update.effective_user.full_name, update.effective_user.username)
    await update.effective_chat.send_message(
        welcome_text(), reply_markup=main_menu_kb(is_admin(update)), parse_mode="Markdown"
    )
    await update.effective_chat.send_message(FEATURES_TEXT, parse_mode="Markdown")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = HELP_TEXT_PUBLIC + (HELP_TEXT_ADMIN_SUFFIX if is_admin(update) else "")
    await update.effective_chat.send_message(text, parse_mode="Markdown")

async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = get_session()
    try:
        u = db.query(User).filter(User.telegram_id == str(update.effective_user.id)).one()
        await update.effective_chat.send_message(settings_text(u), parse_mode="Markdown")
    finally:
        db.close()

async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    txt = (
        f"🆔 Your Telegram ID: `{u.id}`\n"
        f"👤 Name: {u.full_name}\n"
        f"🔗 Username: @{u.username or '(none)'}\n\n"
        + ("👑 You are *admin*." if is_admin(update) else "👤 You are a regular user.")
    )
    await update.effective_chat.send_message(txt, parse_mode="Markdown")

async def addkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.effective_chat.send_message("Usage: /addkeyword <kw1, kw2, ...>")
        return
    kws = parse_keywords_arg(" ".join(context.args))
    db = get_session()
    try:
        u = db.query(User).filter(User.telegram_id == str(update.effective_user.id)).one()
        added = 0
        for k in kws:
            if not db.query(Keyword).filter(Keyword.user_id==u.id, Keyword.keyword==k).one_or_none():
                db.add(Keyword(user_id=u.id, keyword=k)); added += 1
        db.commit()
        lst = ", ".join(sorted([k.keyword for k in u.keywords]))
        await update.effective_chat.send_message(f"Added {added} keywords.\nYour keywords: {lst}")
    finally:
        db.close()

async def delkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.effective_chat.send_message("Usage: /delkeyword <kw>")
        return
    kw = " ".join(context.args).strip().lower()
    db = get_session()
    try:
        u = db.query(User).filter(User.telegram_id == str(update.effective_user.id)).one()
        row = db.query(Keyword).filter(Keyword.user_id==u.id, Keyword.keyword==kw).one_or_none()
        if row:
            db.delete(row); db.commit()
            await update.effective_chat.send_message(f"Removed keyword: {kw}")
        else:
            await update.effective_chat.send_message("Not found.")
    finally:
        db.close()

async def clearkeywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = get_session()
    try:
        u = db.query(User).filter(User.telegram_id == str(update.effective_user.id)).one()
        for r in list(u.keywords):
            db.delete(r)
        db.commit()
        await update.effective_chat.send_message("All keywords cleared.")
    finally:
        db.close()

async def keywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = get_session()
    try:
        u = db.query(User).filter(User.telegram_id == str(update.effective_user.id)).one()
        lst = ", ".join(sorted([k.keyword for k in u.keywords])) or "(none)"
        await update.effective_chat.send_message(f"Your keywords: {lst}")
    finally:
        db.close()

async def setcountry_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = " ".join(context.args) if context.args else "ALL"
    db = get_session()
    try:
        u = db.query(User).filter(User.telegram_id == str(update.effective_user.id)).one()
        u.countries = val or "ALL"; db.commit()
        await update.effective_chat.send_message(f"Countries set to: {u.countries}")
    finally:
        db.close()

async def setproposal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.effective_message.text.partition(" ")[2]
    db = get_session()
    try:
        u = db.query(User).filter(User.telegram_id == str(update.effective_user.id)).one()
        u.proposal_template = text.strip() if text else None
        db.commit()
        await update.effective_chat.send_message("Proposal template saved.")
    finally:
        db.close()

async def platforms_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cc = (context.args[0].upper() if context.args else "ALL")
    if cc == "GR":
        txt = "🇬🇷 *Greece*: JobFind.gr, Skywalker.gr, Kariera.gr"
    else:
        txt = "🌍 *Global*: Freelancer.com, PeoplePerHour, Malt, Workana, Guru, 99designs, Toptal*, Codeable*, YunoJuno*, Worksome*, twago, freelancermap"
    await update.effective_chat.send_message(txt, parse_mode="Markdown")

async def selftest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(
        "🧪 [TEST] Example job card\n\n"
        "*Source:* Freelancer\n*Type:* Fixed\n*Budget:* 100–300 USD\n*~ $100.00–$300.00 USD\n*Bids:* 12\n*Posted:* 0s ago\n\n"
        "Keyword matched: TEST",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 Proposal", url="https://www.freelancer.com/") ,
             InlineKeyboardButton("🔗 Original", url="https://www.freelancer.com/")],
            [InlineKeyboardButton("⭐ Keep", callback_data="keep:test"), InlineKeyboardButton("🗑️ Delete", callback_data="del:test")]
        ])
    )

# ----------------------------------------------------------------------------
# Admin
# ----------------------------------------------------------------------------

async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    db = get_session()
    try:
        users = db.query(User).order_by(User.created_at.desc()).limit(200).all()
        lines = []
        for u in users:
            lines.append(f"• `{u.telegram_id}` {u.name or ''} @{u.username or ''}  active={'yes' if u.is_active() else 'no'}")
        await update.effective_chat.send_message("👥 *Users*\n" + "\n".join(lines), parse_mode="Markdown")
    finally:
        db.close()

async def grant_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    if len(context.args) < 2:
        await update.effective_chat.send_message("Usage: /grant <telegram_id> <days>")
        return
    tg_id = context.args[0]
    days = int(context.args[1])
    db = get_session()
    try:
        u = db.query(User).filter(User.telegram_id == str(tg_id)).one_or_none()
        if not u:
            await update.effective_chat.send_message("User not found.")
            return
        base = u.access_until if u.access_until and u.access_until > now_utc() else now_utc()
        u.access_until = base + timedelta(days=days)
        db.commit()
        await update.effective_chat.send_message(f"Granted until {u.access_until.isoformat(sep=' ', timespec='seconds')} UTC")
    finally:
        db.close()

async def block_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    if not context.args:
        await update.effective_chat.send_message("Usage: /block <telegram_id>")
        return
    db = get_session()
    try:
        u = db.query(User).filter(User.telegram_id == str(context.args[0])).one_or_none()
        if not u: await update.effective_chat.send_message("User not found."); return
        u.is_blocked = True; db.commit()
        await update.effective_chat.send_message("Blocked.")
    finally:
        db.close()

async def unblock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    if not context.args:
        await update.effective_chat.send_message("Usage: /unblock <telegram_id>")
        return
    db = get_session()
    try:
        u = db.query(User).filter(User.telegram_id == str(context.args[0])).one_or_none()
        if not u: await update.effective_chat.send_message("User not found."); return
        u.is_blocked = False; db.commit()
        await update.effective_chat.send_message("Unblocked.")
    finally:
        db.close()

async def feedsstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    flags = []
    for k in ["ENABLE_FREELANCER","ENABLE_PPH","ENABLE_KARIERA","ENABLE_JOBFIND",
              "ENABLE_TWAGO","ENABLE_FREELANCERMAP","ENABLE_YUNOJUNO","ENABLE_WORKSOME",
              "ENABLE_CODEABLE","ENABLE_GURU","ENABLE_99DESIGNS"]:
        flags.append(f"{k}={os.getenv(k,'0')}")
    await update.effective_chat.send_message("Feeds:\n" + "\n".join(flags))

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    msg = update.message.text.partition(" ")[2]
    if not msg:
        await update.effective_chat.send_message("Usage: /broadcast <text>")
        return
    db = get_session()
    try:
        users = db.query(User).all()
        sent = 0
        for u in users:
            try:
                await context.bot.send_message(chat_id=int(u.telegram_id), text=msg)
                sent += 1
            except Exception:
                pass
        await update.effective_chat.send_message(f"Broadcast sent to {sent} users.")
    finally:
        db.close()

# ----------------------------------------------------------------------------
# Buttons / Contact flow
# ----------------------------------------------------------------------------

async def button_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    if data == "mm:addkw":
        await q.message.reply_text("Send `/addkeyword kw1, kw2, kw3`", parse_mode="Markdown")
    elif data == "mm:settings":
        db = get_session()
        try:
            u = db.query(User).filter(User.telegram_id == str(update.effective_user.id)).one()
            await q.message.reply_text(settings_text(u), parse_mode="Markdown")
        finally:
            db.close()
    elif data == "mm:help":
        await q.message.reply_text(HELP_TEXT_PUBLIC + (HELP_TEXT_ADMIN_SUFFIX if is_admin(update) else ""), parse_mode="Markdown")
    elif data.startswith("mm:saved:"):
        page = int(data.split(":")[2])
        await show_saved_jobs(update, context, page)
    elif data == "mm:contact":
        db = get_session()
        try:
            u = db.query(User).filter(User.telegram_id == str(update.effective_user.id)).one()
            th = ContactThread(user_id=u.id, is_open=True)
            db.add(th); db.commit()
        finally:
            db.close()
        await q.message.reply_text("✍️ Please type your message for the admin. I'll forward it right away.")
    elif data.startswith("saved:open:"):
        job_id = int(data.split(":")[2])
        await show_job_card(update, context, job_id)
    elif data.startswith("saved:del:"):
        job_id = int(data.split(":")[2])
        db = get_session()
        try:
            u = db.query(User).filter(User.telegram_id == str(update.effective_user.id)).one()
            row = db.query(SavedJob).filter(SavedJob.user_id==u.id, SavedJob.job_id==job_id).one_or_none()
            if row:
                db.delete(row); db.commit()
                await q.message.reply_text("Deleted from saved.")
        finally:
            db.close()

async def show_saved_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int):
    db = get_session()
    try:
        u = db.query(User).filter(User.telegram_id == str(update.effective_user.id)).one()
        rows = db.query(SavedJob).filter(SavedJob.user_id==u.id).order_by(SavedJob.created_at.desc()).limit(20).all()
        if not rows:
            await update.effective_chat.send_message("No saved jobs yet.")
            return
        for sj in rows:
            job = db.query(Job).filter(Job.id==sj.job_id).one_or_none()
            if not job: continue
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Open", callback_data=f"saved:open:{job.id}"),
                 InlineKeyboardButton("🗑️ Delete", callback_data=f"saved:del:{job.id}")]
            ])
            await update.effective_chat.send_message(f"• {job.source} — {job.title}", reply_markup=kb)
    finally:
        db.close()

async def show_job_card(update: Update, context: ContextTypes.DEFAULT_TYPE, job_id: int):
    db = get_session()
    try:
        job = db.query(Job).filter(Job.id==job_id).one()
        prop = job.proposal_url or job.url
        orig = job.original_url or job.url
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 Proposal", url=prop),
             InlineKeyboardButton("🔗 Original", url=orig)]
        ])
        btxt = ""
        if job.budget_min or job.budget_max:
            cur = job.budget_currency or ""
            rng = f"{job.budget_min or ''}–{job.budget_max or ''} {cur}".strip("– ").strip()
            btxt = f"\n💲 Budget: {rng}"
        await update.effective_chat.send_message(f"*{job.title}*\nSource: {job.source}{btxt}\n\n{(job.description or '')[:400]}…", parse_mode="Markdown", reply_markup=kb)
    finally:
        db.close()

async def contact_flow_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = get_session()
    try:
        u = await ensure_user(context, str(update.effective_user.id), update.effective_user.full_name, update.effective_user.username)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("↩️ Reply", callback_data=f"admreply:{u.telegram_id}"),
             InlineKeyboardButton("🚫 Decline", callback_data=f"admdecline:{u.telegram_id}")]
        ])
        txt = f"📩 *Message from user*\n• ID: `{u.telegram_id}`\n• Name: {u.name}\n• Username: @{u.username or '(none)'}\n\n{update.effective_message.text}"
        if ADMIN_ID:
            await context.bot.send_message(chat_id=int(ADMIN_ID), text=txt, parse_mode="Markdown", reply_markup=kb)
        await update.effective_chat.send_message("✅ Sent to the admin. You’ll receive a reply here.")
    finally:
        db.close()
