import os
from datetime import datetime, timezone
from typing import List
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, ApplicationBuilder,
    CommandHandler, CallbackQueryHandler,
    ContextTypes
)
from db import SessionLocal, User, Keyword, init_db


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def main_menu_kb(is_admin: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("➕ Add Keywords", callback_data="act:addkws"),
         InlineKeyboardButton("⚙️ Settings", callback_data="act:settings")],
        [InlineKeyboardButton("💾 Saved", callback_data="act:saved"),
         InlineKeyboardButton("🆘 Help", callback_data="act:help")],
        [InlineKeyboardButton("☎️ Contact", callback_data="act:contact")]
    ]
    if is_admin:
        rows.append([InlineKeyboardButton("👑 Admin", callback_data="act:admin")])
    return InlineKeyboardMarkup(rows)


def iso_or_dash(dt: datetime | None) -> str:
    if not dt:
        return "—"
    s = dt.astimezone(timezone.utc).isoformat()
    return s.replace("+00:00", "Z")


def settings_card(u: User, kws: List[Keyword]) -> str:
    kws_txt = ", ".join(sorted([k.value for k in kws])) or "—"
    return (
        "⚙️ <b>Your Settings</b>\n\n"
        f"Keywords: {kws_txt}\n"
        f"Countries: {u.countries or 'ALL'}\n"
        f"Trial start: {iso_or_dash(u.trial_start)}\n"
        f"Trial ends: {iso_or_dash(u.trial_end)}\n"
        f"License until: {iso_or_dash(u.license_until)}\n"
        f"Active: {'✅' if u.is_active else '❌'}  "
        f"Blocked: {'🚫' if u.is_blocked else '✅'}"
    )


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = str(update.effective_user.id)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == tg_id).one_or_none()
        if not user:
            now = now_utc()
            user = User(
                telegram_id=tg_id,
                is_active=True,
                is_blocked=False,
                is_admin=False,
                trial_start=now,
                trial_end=None,
                license_until=None,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        kb = main_menu_kb(bool(user.is_admin))
        await update.message.reply_text(
            "👋 Welcome to Freelancer Alert Bot!\n"
            "You can add keywords using /addkeyword python, design, marketing ...",
            parse_mode="HTML", reply_markup=kb
        )
    finally:
        db.close()


async def addkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = (update.message.text or "").split(maxsplit=1)
    if len(raw) < 2:
        await update.message.reply_text("Usage: /addkeyword keyword1, keyword2")
        return
    keywords = [k.strip() for k in raw[1].split(",") if k.strip()]
    if not keywords:
        await update.message.reply_text("No valid keywords found.")
        return
    tg_id = str(update.effective_user.id)
    db = SessionLocal()
    added = 0
    try:
        user = db.query(User).filter(User.telegram_id == tg_id).one_or_none()
        if not user:
            user = User(telegram_id=tg_id, is_active=True, is_blocked=False, is_admin=False)
            db.add(user)
            db.flush()
        for kw in keywords:
            if not db.query(Keyword).filter_by(user_id=user.id, value=kw).first():
                db.add(Keyword(user_id=user.id, value=kw))
                added += 1
        db.commit()
        await update.message.reply_text(f"✅ Added {added} new keywords.")
    except Exception as e:
        db.rollback()
        await update.message.reply_text(f"⚠️ Error: {e}")
    finally:
        db.close()


async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = str(update.effective_user.id)
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.telegram_id == tg_id).one()
        kws = db.query(Keyword).filter(Keyword.user_id == u.id).order_by(Keyword.value).all()
        await update.message.reply_text(settings_card(u, kws), parse_mode="HTML")
    finally:
        db.close()


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "ℹ️ <b>How it works</b>\n\n"
        "• Add keywords: /addkeyword python, telegram\n"
        "• View settings: /mysettings\n"
        "• Set countries: /setcountry US,UK (or ALL)\n"
        "• Proposal template: /setproposal <text>\n"
        "• Contact admin: /contact"
    )
    await update.message.reply_text(msg, parse_mode="HTML")


async def menu_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data or ""
    if data == "act:help":
        await q.message.reply_text("Use /help for usage guide.")
    elif data == "act:addkws":
        await q.message.reply_text("Use /addkeyword python, design")
    elif data == "act:settings":
        await q.message.reply_text("Use /mysettings to view settings.")
    elif data == "act:saved":
        await q.message.reply_text("Saved jobs list coming soon.")
    elif data == "act:contact":
        await q.message.reply_text("Send your message and admin will reply.")
    elif data == "act:admin":
        await q.message.reply_text("Admin menu not yet active.")
    await q.answer()


def build_application() -> Application:
    init_db()
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    if not token or ":" not in token:
        raise RuntimeError("❌ TELEGRAM_TOKEN missing/invalid. Set it in Render → Environment.")
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))
    app.add_handler(CallbackQueryHandler(menu_action_cb, pattern=r"^act:"))
    return app
