import os, asyncio, logging, re
from datetime import datetime, timedelta, timezone
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
from sqlalchemy import text
from db import get_session, get_or_create_user_by_tid, ensure_schema
from db_events import ensure_feed_events_schema, record_event
from db_keywords import list_keywords
from config import ADMIN_IDS, STATS_WINDOW_HOURS, TRIAL_DAYS

log = logging.getLogger("bot")

BOT_TOKEN = os.getenv("BOT_TOKEN")

FX = {"EUR": 1.08, "GBP": 1.25, "USD": 1.0}


def usd_fmt(amount, cur):
    if not amount:
        return "N/A"
    cur = (cur or "USD").upper()
    usd = amount * FX.get(cur, 1)
    if cur == "USD":
        return f"{amount:.2f} USD"
    return f"{amount:.2f} {cur} (~${usd:.2f} USD)"


def is_admin_user(tid: int) -> bool:
    return tid in {int(a) for a in (ADMIN_IDS or [])}


# ---------- MENU HELPERS ----------

def main_menu_kb(is_admin=False):
    rows = [
        [
            InlineKeyboardButton("➕ Add Keywords", callback_data="act:addkw"),
            InlineKeyboardButton("⚙️ Settings", callback_data="act:settings"),
        ],
        [
            InlineKeyboardButton("🆘 Help", callback_data="act:help"),
            InlineKeyboardButton("💾 Saved", callback_data="act:saved"),
        ],
        [InlineKeyboardButton("📨 Contact", callback_data="act:contact")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton("🔥 Admin", callback_data="act:admin")])
    return InlineKeyboardMarkup(rows)


HELP_EN = (
    "🧭 <b>Help / How it works</b>\n\n"
    "1️⃣ Add keywords with <code>/addkeyword logo, python</code>\n"
    "2️⃣ Adjust countries via <code>/setcountry US, UK or ALL</code>\n"
    "3️⃣ Save proposal template with <code>/setproposal text</code>\n\n"
    "When a job appears you can:\n⭐ Save    🗑 Delete   📄 Proposal   🔗 Original\n"
)


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        s.execute(
            'UPDATE "user" SET trial_start=COALESCE(trial_start, NOW()), trial_end=COALESCE(trial_end, NOW()+make_interval(days=>:d)) WHERE id=:i',
            {"i": u.id, "d": TRIAL_DAYS},
        )
        expiry = s.execute(
            'SELECT COALESCE(license_until, trial_end) AS expiry FROM "user" WHERE id=:i',
            {"i": u.id},
        ).fetchone()["expiry"]
        s.commit()
    await update.message.reply_html(
        f"👋 <b>Welcome to Freelancer Alert Bot!</b>\n\n🎁 10-day free trial until {expiry:%Y-%m-%d %H:%M UTC}",
        reply_markup=main_menu_kb(is_admin_user(update.effective_user.id)),
    )
    await update.message.reply_html(HELP_EN)


# ---------- SELF TEST ----------

async def selftest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        now = datetime.now(timezone.utc)
        # job 1
        j1 = (
            "<b>Email Signature from Existing Logo</b>\n"
            f"💰 <b>Budget:</b> 10.0–30.0 USD (~${(20.0):.2f} USD)\n"
            "🌐 <b>Source:</b> Freelancer\n"
            "🔍 <b>Match:</b> logo\n"
            "📝 Please duplicate and make an editable version of my existing email signature based on the logo file\n"
            f"🕓 <b>Posted:</b> {now:%Y-%m-%d %H:%M UTC}"
        )
        kb1 = InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 Proposal", url="https://freelancer.com/job/sample"),
             InlineKeyboardButton("🔗 Original", url="https://freelancer.com/job/sample")],
            [InlineKeyboardButton("⭐ Save", callback_data="job:save"),
             InlineKeyboardButton("🗑 Delete", callback_data="job:delete")]
        ])
        await update.message.reply_html(j1, reply_markup=kb1)
        record_event("freelancer")

        # job 2
        j2 = (
            "<b>Landing Page Development (WordPress)</b>\n"
            f"💰 <b>Budget:</b> 120.00 USD\n"
            "🌐 <b>Source:</b> PeoplePerHour\n"
            "🔍 <b>Match:</b> wordpress\n"
            "📝 Create responsive WordPress landing page for new product launch\n"
            f"🕓 <b>Posted:</b> {now:%Y-%m-%d %H:%M UTC}"
        )
        kb2 = InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 Proposal", url="https://peopleperhour.com/job/sample"),
             InlineKeyboardButton("🔗 Original", url="https://peopleperhour.com/job/sample")],
            [InlineKeyboardButton("⭐ Save", callback_data="job:save"),
             InlineKeyboardButton("🗑 Delete", callback_data="job:delete")]
        ])
        await update.message.reply_html(j2, reply_markup=kb2)
        record_event("peopleperhour")

        await update.message.reply_html("✅ Self-Test completed — 2 sample jobs posted.")
    except Exception as e:
        log.exception(e)
        await update.message.reply_text("⚠️ Self-test failed.")
# ---------- SAVE / DELETE JOBS ----------

def _extract_title(text_html: str) -> str:
    m = re.search(r"<b>([^<]+)</b>", text_html or "", flags=re.I)
    return m.group(1).strip() if m else "Untitled"


async def job_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    msg = q.message
    text_html = msg.text_html or msg.caption_html or msg.text or msg.caption or ""

    if data == "job:save":
        try:
            with get_session() as s:
                u = get_or_create_user_by_tid(s, q.from_user.id)
                s.execute(
                    """CREATE TABLE IF NOT EXISTS saved_job(
                       id SERIAL PRIMARY KEY,
                       user_id BIGINT NOT NULL,
                       title TEXT,
                       description TEXT,
                       platform TEXT,
                       budget_amount FLOAT,
                       budget_currency TEXT,
                       saved_at TIMESTAMP DEFAULT (NOW() AT TIME ZONE 'UTC'))"""
                )
                title = _extract_title(text_html)
                s.execute(
                    text("INSERT INTO saved_job(user_id,title,description,platform,budget_amount,budget_currency)"
                         " VALUES(:u,:t,:d,:p,:b,:c)"),
                    {"u": u.id, "t": title, "d": text_html, "p": "manual", "b": None, "c": "USD"},
                )
                s.commit()
            # auto-remove message after save
            await msg.delete()
        except Exception as e:
            log.exception("Save error %s", e)
        return

    if data == "job:delete":
        try:
            await msg.delete()
        except Exception:
            pass
        return


# ---------- SAVED LIST ----------

async def saved_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        with get_session() as s:
            u = get_or_create_user_by_tid(s, update.effective_user.id)
            rows = s.execute(
                text("SELECT title,description,saved_at FROM saved_job WHERE user_id=:u ORDER BY saved_at DESC"),
                {"u": u.id},
            ).fetchall()
        if not rows:
            await update.message.reply_text("💾 No saved jobs yet.")
            return
        for r in rows:
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Original", url="https://freelancer.com")],
                [InlineKeyboardButton("🗑 Delete", callback_data="saved:del")]
            ])
            await update.message.reply_html(r["description"], reply_markup=kb)
            await asyncio.sleep(0.3)
    except Exception as e:
        log.exception("Saved list error %s", e)
        await update.message.reply_text("⚠️ Saved list unavailable.")


async def saved_delete_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    with get_session() as s:
        u = get_or_create_user_by_tid(s, q.from_user.id)
        s.execute(text("DELETE FROM saved_job WHERE user_id=:u"), {"u": u.id})
        s.commit()
    await q.message.delete()
# ---------- MENU / ROUTER ----------

async def menu_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    await q.answer()
    if data == "act:saved":
        await saved_cmd(update, context)
    elif data == "act:help":
        await q.message.reply_html(HELP_EN)
    elif data == "act:addkw":
        await q.message.reply_text("Use /addkeyword to add keywords.")
    else:
        await q.message.reply_text("Menu coming soon.")


# ---------- APPLICATION BUILDER ----------

def build_application() -> Application:
    ensure_schema()
    ensure_feed_events_schema()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("selftest", selftest_cmd))
    app.add_handler(CommandHandler("saved", saved_cmd))
    app.add_handler(CallbackQueryHandler(job_action_cb, pattern=r"^job:(save|delete)$"))
    app.add_handler(CallbackQueryHandler(saved_delete_cb, pattern=r"^saved:del$"))
    app.add_handler(CallbackQueryHandler(menu_action_cb, pattern=r"^act:"))
    return app
