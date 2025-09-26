import os
import logging
import re
from typing import List, Optional

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from db import SessionLocal, User, Keyword, JobSaved, JobDismissed

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN is not set.")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [bot] %(levelname)s: %(message)s")
logger = logging.getLogger("freelancer-bot")

_SPLIT_RE = re.compile(r"[,\n]+")

WELCOME = (
    "👋 *Welcome to Freelancer Alerts Bot!*\n\n"
    "Get real-time job alerts based on your keywords and country filters.\n\n"
    "👉 Use the menu below or commands to configure your settings."
)

HELP = (
    "📖 *Help / How it works*\n\n"
    "1️⃣ Add keywords with `/addkeyword python, telegram`\n"
    "2️⃣ Set your countries with `/setcountry US,UK` (or `ALL`)\n"
    "3️⃣ Save a proposal template with `/setproposal <text>`\n"
    "   Placeholders you can use: {job_title}, {experience}, {stack}, {availability}, {step1}, {step2}, {step3}, {budget_time}, {portfolio}, {name}\n"
    "4️⃣ When a job arrives you can:\n"
    "   • ⭐ Save it\n"
    "   • 🙈 Dismiss it\n"
    "   • 💼 Proposal → *direct affiliate link to job*\n"
    "   • 🔗 Original → *same affiliate-wrapped job link*\n\n"
    "⚙️ Use `/mysettings` anytime to check your filters and proposal."
)

# ---------------------------
# Helpers
# ---------------------------
def normalize_kw_list(text: str) -> List[str]:
    out: List[str] = []
    seen = set()
    for part in _SPLIT_RE.split(text or ""):
        p = part.strip()
        if not p:
            continue
        low = p.lower()
        if low not in seen:
            seen.add(low)
            out.append(p)
    return out


async def reply_usage(update: Update, text: str):
    await update.effective_message.reply_text(text)


def list_keywords(db, user_id: int) -> List[str]:
    rows = db.query(Keyword).filter_by(user_id=user_id).order_by(Keyword.keyword.asc()).all()
    return [r.keyword for r in rows]


async def ensure_user(db, telegram_id: int) -> User:
    row = db.query(User).filter_by(telegram_id=telegram_id).first()
    if not row:
        row = User(telegram_id=telegram_id, countries="ALL")
        db.add(row)
        db.commit()
        db.refresh(row)
    return row

# ---------------------------
# Menus
# ---------------------------
def main_menu_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("➕ Add Keywords", callback_data="menu:add"),
                InlineKeyboardButton("🛠 Settings", callback_data="menu:settings"),
            ],
            [
                InlineKeyboardButton("📖 Help", callback_data="menu:help"),
            ],
        ]
    )

# ---------------------------
# Commands
# ---------------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(WELCOME, reply_markup=main_menu_markup(), parse_mode="Markdown")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(HELP, reply_markup=main_menu_markup(), parse_mode="Markdown")


async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        user = await ensure_user(db, update.effective_user.id)
        kws = list_keywords(db, user.id)
        countries = user.countries or "ALL"
        tmpl = (user.proposal_template or "(none)")[:250]
        await update.effective_message.reply_text(
            f"🛠 *Your Settings*\n"
            f"• Keywords: {', '.join(kws) if kws else '(none)'}\n"
            f"• Countries: {countries}\n"
            f"• Proposal template: {tmpl}",
            parse_mode="Markdown",
        )
    finally:
        db.close()


async def setcountry_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        return await reply_usage(update, "Usage: /setcountry <US,UK,DE> or ALL")
    val = " ".join(args).upper().replace(" ", "")
    db = SessionLocal()
    try:
        user = await ensure_user(db, update.effective_user.id)
        user.countries = val
        db.commit()
        await update.effective_message.reply_text(f"✅ Countries set to: {val}")
    finally:
        db.close()


async def addkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text:
        return await reply_usage(update, "Usage: /addkeyword <word[,word2,...]>")
    new_kws = normalize_kw_list(text)
    if not new_kws:
        return await update.effective_message.reply_text("No valid keywords found.")
    db = SessionLocal()
    added = []
    try:
        user = await ensure_user(db, update.effective_user.id)
        existing = set(k.lower() for k in list_keywords(db, user.id))
        for kw in new_kws:
            if kw.lower() in existing:
                continue
            db.add(Keyword(user_id=user.id, keyword=kw))
            added.append(kw)
        db.commit()
        if added:
            await update.effective_message.reply_text(f"✅ Added: {', '.join(added)}")
        else:
            await update.effective_message.reply_text("No new keywords added (all duplicates).")
    finally:
        db.close()


async def keywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        user = await ensure_user(db, update.effective_user.id)
        kws = list_keywords(db, user.id)
        await update.effective_message.reply_text(
            "📚 Keywords:\n" + ("\n".join(f"• {k}" for k in kws) if kws else "(none)")
        )
    finally:
        db.close()


async def clearkeywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("✅ Confirm", callback_data="conf:clear_kws")],
         [InlineKeyboardButton("❌ Cancel", callback_data="conf:cancel")]]
    )
    await update.effective_message.reply_text("Are you sure you want to delete all keywords?", reply_markup=kb)


async def delkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await reply_usage(update, "Usage: /delkeyword <keyword>")
    name = " ".join(context.args).strip()
    db = SessionLocal()
    try:
        user = await ensure_user(db, update.effective_user.id)
        row = None
        for k in list_keywords(db, user.id):
            if k.lower() == name.lower():
                row = db.query(Keyword).filter_by(user_id=user.id, keyword=k).first()
                break
        if not row:
            return await update.effective_message.reply_text(f"Not found: {name}")
        db.delete(row)
        db.commit()
        await update.effective_message.reply_text(f"🗑 Deleted keyword: {name}")
    finally:
        db.close()


async def setproposal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args).strip()
    if not text:
        return await reply_usage(update, "Usage: /setproposal <text>")
    if len(text) > 6000:
        return await update.effective_message.reply_text("Template too long (max ~6000 chars).")
    db = SessionLocal()
    try:
        user = await ensure_user(db, update.effective_user.id)
        user.proposal_template = text
        db.commit()
        await update.effective_message.reply_text("✅ Proposal template saved.")
    finally:
        db.close()


async def savejob_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await reply_usage(update, "Usage: /savejob <job_id>")
    job_id = context.args[0][:64]
    db = SessionLocal()
    try:
        user = await ensure_user(db, update.effective_user.id)
        if not db.query(JobSaved).filter_by(user_id=user.id, job_id=job_id).first():
            db.add(JobSaved(user_id=user.id, job_id=job_id))
            db.commit()
        await update.effective_message.reply_text(f"⭐ Saved job: {job_id}")
    finally:
        db.close()


async def dismissjob_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await reply_usage(update, "Usage: /dismissjob <job_id>")
    job_id = context.args[0][:64]
    db = SessionLocal()
    try:
        user = await ensure_user(db, update.effective_user.id)
        if not db.query(JobDismissed).filter_by(user_id=user.id, job_id=job_id).first():
            db.add(JobDismissed(user_id=user.id, job_id=job_id))
            db.commit()
        await update.effective_message.reply_text(f"🙈 Dismissed job: {job_id}")
    finally:
        db.close()

# ---------------------------
# Callback buttons (only menu + confirm left)
# ---------------------------
async def confirm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    if data == "conf:clear_kws":
        db = SessionLocal()
        try:
            user = await ensure_user(db, update.effective_user.id)
            db.query(Keyword).filter_by(user_id=user.id).delete()
            db.commit()
            await q.edit_message_text("✅ All keywords cleared.")
        finally:
            db.close()
    elif data == "conf:cancel":
        await q.edit_message_text("❌ Cancelled.")


async def button_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    if data == "menu:add":
        await q.message.reply_text("Use `/addkeyword <word[,word2,...]>` to add keywords.", parse_mode="Markdown")
    elif data == "menu:settings":
        await mysettings_cmd(update, context)
    elif data == "menu:help":
        await help_cmd(update, context)

# ---------------------------
# Main
# ---------------------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))
    app.add_handler(CommandHandler("setcountry", setcountry_cmd))
    app.add_handler(CommandHandler("setproposal", setproposal_cmd))

    app.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app.add_handler(CommandHandler("keywords", keywords_cmd))
    app.add_handler(CommandHandler("listkeywords", keywords_cmd))
    app.add_handler(CommandHandler("delkeyword", delkeyword_cmd))
    app.add_handler(CommandHandler("clearkeywords", clearkeywords_cmd))

    app.add_handler(CommandHandler("savejob", savejob_cmd))
    app.add_handler(CommandHandler("dismissjob", dismissjob_cmd))

    app.add_handler(CallbackQueryHandler(button_cb, pattern=r"^menu:"))
    app.add_handler(CallbackQueryHandler(confirm_cb, pattern=r"^conf:(clear_kws|cancel)$"))

    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
