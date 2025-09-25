import os
import logging
import re
from typing import List, Optional

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from db import SessionLocal, User, Keyword, JobSaved, JobDismissed

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DEBUG = os.getenv("DEBUG", "0") == "1"

logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s [bot] %(levelname)s: %(message)s",
)
logger = logging.getLogger("freelancer-bot")

# --------- Helpers ---------
_SPLIT_RE = re.compile(r"[,\n]+")

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

async def ensure_user(db, tg_id: int) -> User:
    user = db.query(User).filter_by(telegram_id=tg_id).first()
    if not user:
        user = User(telegram_id=tg_id)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user

def list_keywords(db, user_id: int) -> List[str]:
    rows = db.query(Keyword).filter_by(user_id=user_id).order_by(Keyword.id.asc()).all()
    return [r.keyword for r in rows]

def find_keyword_row(db, user_id: int, name_ci: str) -> Optional[Keyword]:
    for row in db.query(Keyword).filter_by(user_id=user_id).all():
        if row.keyword.lower() == name_ci.lower():
            return row
    return None

# --------- Commands ---------
WELCOME = (
    "👋 Welcome to Freelancer Alerts Bot!\n\n"
    "Commands:\n"
    "/addkeyword <word[,word2,...]> – Add keywords (comma-separated)\n"
    "/keywords – List your keywords\n"
    "/delkeyword <word> – Delete a keyword\n"
    "/editkeyword <old> -> <new> – Rename a keyword\n"
    "/clearkeywords – Delete all keywords (confirmation)\n"
    "/setcountry <US,UK,DE> – Country filter (or ALL)\n"
    "/mysettings – Show your filters\n"
    "/setproposal <text> – Save your proposal template\n"
    "   Placeholders: {job_title}, {experience}, {stack}, {availability}, {step1}, {step2}, {step3}, {budget_time}, {portfolio}, {name}\n"
    "/savejob <job_id> – Save a job (same as ⭐ Keep)\n"
    "/dismissjob <job_id> – Dismiss a job (same as 🙈 Dismiss)\n"
    "/clearjob <job_id> – Alias of /dismissjob\n\n"
    "Tips: Alerts have inline buttons ⭐ Keep / 🙈 Dismiss / ✍️ Proposal."
)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(WELCOME)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(WELCOME)

async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        user = await ensure_user(db, update.effective_user.id)
        kws = list_keywords(db, user.id)
        countries = user.countries or "ALL"
        tmpl = (user.proposal_template or "(none)")[:250]
        await update.effective_message.reply_text(
            f"🛠 Settings\n"
            f"• Keywords: {', '.join(kws) if kws else '(none)'}\n"
            f"• Countries: {countries}\n"
            f"• Proposal template: {tmpl}"
        )
    finally:
        db.close()

async def setcountry_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        return await reply_usage(update, "Usage: /setcountry <US,UK,DE> or ALL")
    value = " ".join(args).strip()
    db = SessionLocal()
    try:
        user = await ensure_user(db, update.effective_user.id)
        user.countries = value.upper()
        db.commit()
        await update.effective_message.reply_text(f"✅ Countries set to: {user.countries}")
    finally:
        db.close()

async def addkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await reply_usage(update, "Usage: /addkeyword <keyword[,keyword2,...]>")
    raw = " ".join(context.args)
    to_add = normalize_kw_list(raw)
    db = SessionLocal()
    added = []
    try:
        user = await ensure_user(db, update.effective_user.id)
        existing_ci = {k.lower() for k in list_keywords(db, user.id)}
        for kw in to_add:
            if kw.lower() in existing_ci:
                continue
            row = Keyword(user_id=user.id, keyword=kw)
            db.add(row)
            added.append(kw)
        db.commit()
        if added:
            await update.effective_message.reply_text(f"✅ Keyword(s) added: {', '.join(added)}")
        else:
            await update.effective_message.reply_text("ℹ️ Nothing to add (already present).")
    finally:
        db.close()

async def keywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        user = await ensure_user(db, update.effective_user.id)
        kws = list_keywords(db, user.id)
        if not kws:
            await update.effective_message.reply_text("No keywords yet. Add with /addkeyword <word>.")
        else:
            await update.effective_message.reply_text("📎 Your keywords:\n• " + "\n• ".join(kws))
    finally:
        db.close()

async def delkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await reply_usage(update, "Usage: /delkeyword <keyword>")
    name = " ".join(context.args).strip()
    db = SessionLocal()
    try:
        user = await ensure_user(db, update.effective_user.id)
        row = find_keyword_row(db, user.id, name)
        if not row:
            return await update.effective_message.reply_text(f"Not found: {name}")
        db.delete(row)
        db.commit()
        await update.effective_message.reply_text(f"🗑 Deleted keyword: {row.keyword}")
    finally:
        db.close()

async def editkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    m = re.match(r"(.+?)\s*->\s*(.+)", text) if text else None
    if not m:
        return await reply_usage(update, "Usage: /editkeyword <old> -> <new>")
    old, new = m.group(1).strip(), m.group(2).strip()
    if not new:
        return await reply_usage(update, "New keyword cannot be empty.")
    db = SessionLocal()
    try:
        user = await ensure_user(db, update.effective_user.id)
        row = find_keyword_row(db, user.id, old)
        if not row:
            return await update.effective_message.reply_text(f"Not found: {old}")
        exists = find_keyword_row(db, user.id, new)
        if exists and exists.id != row.id:
            return await update.effective_message.reply_text(f"'{new}' already exists.")
        row.keyword = new
        db.commit()
        await update.effective_message.reply_text(f"✏️ Renamed: {old} → {new}")
    finally:
        db.close()

async def clearkeywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Yes, delete all", callback_data="conf:clear_kws"),
          InlineKeyboardButton("Cancel", callback_data="conf:cancel")]]
    )
    await update.effective_message.reply_text("⚠️ Delete ALL your keywords?", reply_markup=kb)

async def confirm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    if data == "conf:cancel":
        return await q.edit_message_text("Cancelled.")
    if data == "conf:clear_kws":
        db = SessionLocal()
        try:
            user = await ensure_user(db, q.from_user.id)
            db.query(Keyword).filter_by(user_id=user.id).delete(synchronize_session=False)
            db.commit()
            await q.edit_message_text("🧹 All keywords deleted.")
        finally:
            db.close()

async def setproposal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await reply_usage(update, "Usage: /setproposal <your proposal template>")
    text = " ".join(context.args)
    db = SessionLocal()
    try:
        user = await ensure_user(db, update.effective_user.id)
        user.proposal_template = text
        db.commit()
        await update.effective_message.reply_text("✅ Proposal template saved.")
    finally:
        db.close()

async def savejob_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return await reply_usage(update, "Usage: /savejob <job_id>")
    job_id = context.args[0]
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
    if not context.args: return await reply_usage(update, "Usage: /dismissjob <job_id>")
    job_id = context.args[0]
    db = SessionLocal()
    try:
        user = await ensure_user(db, update.effective_user.id)
        if not db.query(JobDismissed).filter_by(user_id=user.id, job_id=job_id).first():
            db.add(JobDismissed(user_id=user.id, job_id=job_id))
            db.commit()
        await update.effective_message.reply_text(f"🙈 Dismissed job: {job_id}")
    finally:
        db.close()

async def clearjob_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await dismissjob_cmd(update, context)

async def button_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    db = SessionLocal()
    try:
        user = await ensure_user(db, q.from_user.id)

        if data.startswith("save:"):
            jid = data.split(":", 1)[1]
            if not db.query(JobSaved).filter_by(user_id=user.id, job_id=jid).first():
                db.add(JobSaved(user_id=user.id, job_id=jid))
                db.commit()
            await q.edit_message_reply_markup(reply_markup=None)
            await q.message.reply_text(f"⭐ Saved job: {jid}")

        elif data.startswith("dismiss:"):
            jid = data.split(":", 1)[1]
            if not db.query(JobDismissed).filter_by(user_id=user.id, job_id=jid).first():
                db.add(JobDismissed(user_id=user.id, job_id=jid))
                db.commit()
            await q.edit_message_reply_markup(reply_markup=None)
            await q.message.reply_text(f"🙈 Dismissed job: {jid}")

        elif data.startswith("proposal:"):
            try:
                _, payload = data.split(":", 1)
                job_id, platform, link, title_enc = payload.split("|", 3)
            except Exception:
                return
            title = re.sub(r"\s+", " ", re.sub(r"%[0-9A-Fa-f]{2}", " ", title_enc))
            tmpl = user.proposal_template or "Hello,\nI’m interested in {job_title}.\nBest regards,"
            msg = tmpl.format(
                job_title=title,
                experience="",
                stack="",
                availability="",
                step1="",
                step2="",
                step3="",
                budget_time="",
                portfolio="",
                name="",
            )
            await q.message.reply_text(f"✍️ Proposal draft:\n\n{msg}")
    finally:
        db.close()

def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is empty.")
        raise SystemExit(1)

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
    app.add_handler(CommandHandler("editkeyword", editkeyword_cmd))
    app.add_handler(CommandHandler("clearkeywords", clearkeywords_cmd))

    app.add_handler(CommandHandler("savejob", savejob_cmd))
    app.add_handler(CommandHandler("dismissjob", dismissjob_cmd))
    app.add_handler(CommandHandler("clearjob", clearjob_cmd))

    app.add_handler(CallbackQueryHandler(button_cb, pattern=r"^(save:|dismiss:|proposal:)"))
    app.add_handler(CallbackQueryHandler(confirm_cb, pattern=r"^conf:(clear_kws|cancel)$"))

    # IMPORTANT: single polling instance
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
