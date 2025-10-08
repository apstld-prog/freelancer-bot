import os
from datetime import datetime, timezone
from typing import List

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from db import SessionLocal, User, Keyword, init_db


# ---------- helpers ----------
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def main_menu_kb(is_admin: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("➕ Add Keywords", callback_data="act:addkws"),
            InlineKeyboardButton("⚙️ Settings", callback_data="act:settings"),
        ],
        [
            InlineKeyboardButton("🆘 Help", callback_data="act:help"),
            InlineKeyboardButton("💾 Saved", callback_data="act:saved"),
        ],
        [
            InlineKeyboardButton("☎️ Contact", callback_data="act:contact"),
            InlineKeyboardButton("👑 Admin", callback_data="act:admin"),
        ],
    ]
    if not is_admin:
        # κουμπί admin δεν θα εμφανίζεται χωρίς access, αλλά αφήνουμε ίδιο layout
        pass
    return InlineKeyboardMarkup(rows)


def settings_card(u: User, kws: List[Keyword]) -> str:
    kws_txt = ", ".join(sorted([k.value for k in kws])) or "—"
    trial_start = u.trial_start.isoformat().replace("+00:00", "Z") if u.trial_start else "None"
    trial_end = u.trial_end.isoformat().replace("+00:00", "Z") if u.trial_end else "None"
    license_until = u.license_until.isoformat().replace("+00:00", "Z") if u.license_until else "None"
    active = "✅" if u.is_active else "❌"
    blocked = "❌" if u.is_blocked else "✅"
    return (
        "🛠️ <b>Your Settings</b>\n"
        f"• Keywords: {kws_txt}\n"
        f"• Countries: {u.countries or 'ALL'}\n"
        f"• Proposal template: {(u.proposal_template or '(none)')}\n\n"
        f"Trial start: {trial_start}\n"
        f"Trial ends: {trial_end}\n"
        f"License until: {license_until}\n"
        f"Expires: {trial_end if trial_end!='None' else 'None'}\n"
        f"Active: {active}   Blocked: {blocked}\n\n"
        "Platforms monitored:\n"
        '<a href="https://www.freelancer.com">Freelancer.com</a>, PeoplePerHour, Malt, Workana, '
        "Guru, 99designs, Toptal*, Codeable*, YunoJuno*, Worksome*, twago, freelancermap (*referral/curated)\n\n"
        "Greece: JobFind.gr, Skywalker.gr, Kariera.gr\n\n"
        "When your trial ends, please contact the admin to extend your access."
    )


# ---------- commands ----------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = str(update.effective_user.id)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == tg_id).one_or_none()
        if not user:
            user = User(telegram_id=tg_id, is_active=True, is_blocked=False, is_admin=False)
            db.add(user)
            db.commit()
            db.refresh(user)
        kb = main_menu_kb(bool(user.is_admin))
        text = (
            "👋 <b>Welcome to Freelancer Alert Bot!</b>\n\n"
            "🎁 <b>You have a 10-day free trial.</b>\n"
            "Automatically finds matching freelance jobs from top platforms and sends you instant alerts.\n\n"
            "Use <code>/help</code> to see how it works."
        )
        await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
    finally:
        db.close()


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🧰 <b>Help / How it works</b>\n\n"
        "1️⃣ Add keywords with <code>/addkeyword python, telegram</code> (comma-separated, English or Greek).\n"
        "2️⃣ Set your countries with <code>/setcountry US,UK</code> (or <code>ALL</code>).\n"
        "3️⃣ Save a proposal template with <code>/setproposal &lt;text&gt;</code> —\n"
        "   Placeholders: {jobtitle}, {experience}, {stack}, {availability}, {step1}, {step2}, {step3}, "
        "{budgettime}, {portfolio}, {name}.\n"
        "4️⃣ When a job arrives you can:\n"
        "   ⭐ Keep it\n"
        "   🗑️ Delete it\n"
        "   📨 Proposal → direct link to job\n"
        "   🔗 Original → same wrapped job link\n\n"
        "► Use <code>/mysettings</code> anytime to check your filters and proposal.\n"
        "► <code>/selftest</code> for a test job.\n"
        "► <code>/platforms CC</code> to see platforms by country (e.g., <code>/platforms GR</code>)."
    )
    await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)


async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = str(update.effective_user.id)
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.telegram_id == tg_id).one()
        kws = db.query(Keyword).filter(Keyword.user_id == u.id).order_by(Keyword.value).all()
        await update.message.reply_text(settings_card(u, kws), parse_mode="HTML", disable_web_page_preview=True)
    finally:
        db.close()


async def addkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add keywords: /addkeyword python, telegram"""
    from sqlalchemy.exc import IntegrityError

    raw_text = (update.message.text or "")
    parts = raw_text.split(maxsplit=1)
    if len(parts) < 2:
        await update.message.reply_text("Usage: /addkeyword python, telegram")
        return

    raw_values = parts[1]
    values = [v.strip() for v in raw_values.split(",") if v.strip()]
    if not values:
        await update.message.reply_text("No keywords provided.")
        return

    tg_id = str(update.effective_user.id)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == tg_id).one_or_none()
        if not user:
            user = User(telegram_id=tg_id, is_active=True, is_blocked=False, is_admin=False)
            db.add(user)
            db.flush()

        added = 0
        for v in values:
            kw = Keyword(user_id=user.id, value=v)
            db.add(kw)
            try:
                db.flush()
                added += 1
            except IntegrityError:
                db.rollback()  # duplicate keyword for same user

        db.commit()
        msg = f"Added {added} keyword(s)." if added else "Nothing new to add."
        await update.message.reply_text(msg)
    except Exception as e:
        db.rollback()
        await update.message.reply_text(f"⚠️ Error while adding: {e}")
    finally:
        db.close()


# ---------- menu callbacks ----------
async def menu_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data or ""
    tg_id = str(update.effective_user.id)

    if data == "act:settings":
        db = SessionLocal()
        try:
            u = db.query(User).filter(User.telegram_id == tg_id).one()
            kws = db.query(Keyword).filter(Keyword.user_id == u.id).order_by(Keyword.value).all()
            await q.message.reply_text(settings_card(u, kws), parse_mode="HTML", disable_web_page_preview=True)
        finally:
            db.close()
        await q.answer()
        return

    if data == "act:help":
        await q.message.reply_text("Use /help to view the full guide.", parse_mode="HTML")
        await q.answer()
        return

    if data == "act:addkws":
        await q.message.reply_text("Add with: /addkeyword python, telegram")
        await q.answer()
        return

    if data == "act:saved":
        await q.message.reply_text("Saved list coming soon.")
        await q.answer()
        return

    if data == "act:contact":
        await q.message.reply_text("Send your message here and an admin will reply.")
        await q.answer()
        return

    if data == "act:admin":
        await q.message.reply_text("Admin panel: use /users, /grant <id> <days>, /block <id>, /unblock <id>, /feedstatus.")
        await q.answer()
        return

    await q.answer()


# ---------- application ----------
def build_application() -> Application:
    init_db()  # ensure schema

    token = os.getenv("TELEGRAM_TOKEN")
    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))
    app.add_handler(CommandHandler("addkeyword", addkeyword_cmd))

    app.add_handler(CallbackQueryHandler(menu_action_cb, pattern=r"^act:"))
    return app
