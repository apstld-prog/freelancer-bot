# bot.py — Full fixed Render version (Saved + Contact restored)
import os, logging, asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Set, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, Application, CommandHandler,
    CallbackQueryHandler, MessageHandler, ContextTypes, filters,
)
try:
    from telegram.ext import JobQueue
except Exception:
    JobQueue = None  # type: ignore
from sqlalchemy import text
from db import ensure_schema, get_session, get_or_create_user_by_tid
from config import ADMIN_IDS, TRIAL_DAYS, STATS_WINDOW_HOURS
from db_events import ensure_feed_events_schema, get_platform_stats, record_event
from db_keywords import (
    list_keywords, add_keywords, count_keywords,
    ensure_keyword_unique, delete_keywords, clear_keywords
)

log = logging.getLogger("bot")
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN env var is required")

# ---------- Admin helpers ----------
def get_db_admin_ids() -> Set[int]:
    try:
        with get_session() as s:
            s.execute(text('SELECT telegram_id FROM "user" WHERE is_admin=TRUE'))
            ids = [r["telegram_id"] for r in s.fetchall()]
        return {int(x) for x in ids if x}
    except Exception:
        return set()

def all_admin_ids() -> Set[int]:
    return set(int(x) for x in (ADMIN_IDS or [])) | get_db_admin_ids()

def is_admin_user(tid: int) -> bool:
    return tid in all_admin_ids()

# ---------- UI ----------
def main_menu_kb(is_admin: bool=False) -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("➕ Add Keywords", callback_data="act:addkw"),
         InlineKeyboardButton("⚙️ Settings", callback_data="act:settings")],
        [InlineKeyboardButton("🆘 Help", callback_data="act:help"),
         InlineKeyboardButton("💾 Saved", callback_data="act:saved")],
        [InlineKeyboardButton("📨 Contact", callback_data="act:contact")],
    ]
    if is_admin:
        kb.append([InlineKeyboardButton("🔥 Admin", callback_data="act:admin")])
    return InlineKeyboardMarkup(kb)

HELP_EN = (
    "<b>🧭 Help / How it works</b>\n\n"
    "<b>Keywords</b>\n"
    "• Add: <code>/addkeyword logo, lighting, sales</code>\n"
    "• Remove: <code>/delkeyword logo, sales</code>\n"
    "• Clear all: <code>/clearkeywords</code>\n\n"
    "<b>Other</b>\n"
    "• Set countries: <code>/setcountry US,UK</code> or <code>ALL</code>\n"
    "• Save proposal: <code>/setproposal &lt;text&gt;</code>\n"
    "• Test card: <code>/selftest</code>\n"
)

def help_footer(hours: int) -> str:
    return (
        "\n<b>🛰 Platforms monitored:</b>\n"
        "• Global: Freelancer.com, PeoplePerHour, Malt, Workana, Guru, 99designs, "
        "Toptal, Codeable, YunoJuno, Worksome, twago, freelancermap\n"
        "• Greece: JobFind.gr, Skywalker.gr, Kariera.gr\n\n"
        "<b>👑 Admin:</b> /users /grant /block /unblock /broadcast /feedstatus\n"
    )

def welcome_text(expiry: Optional[datetime]) -> str:
    extra = f"\n<b>Free trial ends:</b> {expiry.strftime('%Y-%m-%d %H:%M UTC')}" if expiry else ""
    return (
        "<b>👋 Welcome to Freelancer Alert Bot!</b>\n\n"
        "🎁 You have a <b>10-day free trial</b>.\n"
        "The bot finds freelance jobs from top platforms and sends alerts instantly."
        f"{extra}\n\nUse /help for instructions.\n"
    )
def settings_text(keywords: List[str], countries: str|None, proposal_template: str|None,
                  trial_start, trial_end, license_until, active: bool, blocked: bool) -> str:
    def b(v): return "✅" if v else "❌"
    k = ", ".join(keywords) if keywords else "(none)"
    c = countries or "ALL"
    pt = "(none)" if not proposal_template else "(saved)"
    ts = trial_start.isoformat().replace("+00:00","Z") if trial_start else "—"
    te = trial_end.isoformat().replace("+00:00","Z") if trial_end else "—"
    lic = "None" if not license_until else license_until.isoformat().replace("+00:00","Z")
    return (
        f"<b>🛠 Your Settings</b>\n• Keywords: {k}\n• Countries: {c}\n• Proposal: {pt}\n\n"
        f"Start: {ts}\nTrial ends: {te}\nLicense: {lic}\nActive: {b(active)}  Blocked: {b(blocked)}"
    )

# ---------- /start ----------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        s.execute('UPDATE "user" SET trial_start = COALESCE(trial_start, NOW()) WHERE id=%(id)s;', {"id": u.id})
        s.execute(
            'UPDATE "user" SET trial_end = COALESCE(trial_end, NOW() + make_interval(days => %(days)s)) WHERE id=%(id)s;',
            {"id": u.id, "days": TRIAL_DAYS})
        s.execute('SELECT COALESCE(license_until, trial_end) AS expiry FROM "user" WHERE id=%(id)s;', {"id": u.id})
        row = s.fetchone()
        expiry = row["expiry"] if row else None
        s.commit()

    await update.effective_chat.send_message(
        welcome_text(expiry if isinstance(expiry, datetime) else None),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_kb(is_admin=is_admin_user(update.effective_user.id)),
    )
    await update.effective_chat.send_message(
        HELP_EN + help_footer(STATS_WINDOW_HOURS),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )

# ---------- whoami ----------
async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Your Telegram ID: <code>{update.effective_user.id}</code>", parse_mode=ParseMode.HTML)

# ---------- My Settings ----------
async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        kws = list_keywords(u.id)
        s.execute(text(
            'SELECT countries, proposal_template, trial_start, trial_end, license_until, is_active, is_blocked '
            'FROM "user" WHERE id=:id'), {"id": u.id})
        row = s.fetchone()
    await update.effective_chat.send_message(
        settings_text(kws, row["countries"], row["proposal_template"], row["trial_start"],
                      row["trial_end"], row["license_until"], bool(row["is_active"]), bool(row["is_blocked"])),
        parse_mode=ParseMode.HTML, disable_web_page_preview=True)

# ---------- Keyword management ----------
def _parse_keywords(raw: str) -> List[str]:
    parts = [p.strip() for chunk in raw.split(",") for p in chunk.split() if p.strip()]
    seen, out = set(), []
    for p in parts:
        lp = p.lower()
        if lp not in seen:
            seen.add(lp)
            out.append(p)
    return out

async def addkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Add keywords separated by commas. Example:\n<code>/addkeyword logo, lighting</code>", parse_mode=ParseMode.HTML); return
    kws = _parse_keywords(" ".join(context.args))
    if not kws:
        await update.message.reply_text("No valid keywords provided."); return
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
    inserted = add_keywords(u.id, kws)
    current = list_keywords(u.id)
    msg = f"✅ Added {inserted} new keyword(s)." if inserted > 0 else "ℹ️ Those keywords already exist (no changes)."
    await update.message.reply_text(msg + "\n\nCurrent keywords:\n• " + (", ".join(current) if current else "—"), parse_mode=ParseMode.HTML)

async def delkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Delete keywords. Example:\n<code>/delkeyword logo, sales</code>", parse_mode=ParseMode.HTML); return
    kws = _parse_keywords(" ".join(context.args))
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
    removed = delete_keywords(u.id, kws)
    left = list_keywords(u.id)
    await update.message.reply_text(f"🗑 Removed {removed} keyword(s).\n\nCurrent keywords:\n• " + (", ".join(left) if left else "—"), parse_mode=ParseMode.HTML)

async def clearkeywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Yes, clear all", callback_data="kw:clear:yes"),
                                InlineKeyboardButton("❌ No", callback_data="kw:clear:no")]])
    await update.message.reply_text("Clear ALL your keywords?", reply_markup=kb)

# ---------- Self-test ----------
async def selftest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        job_text = (
            "<b>Email Signature from Existing Logo</b>\n<b>Budget:</b> 10.0–30.0 USD\n<b>Source:</b> Freelancer\n<b>Match:</b> logo\n✏️ Please create an editable version of the email signature based on the provided logo.\n"
        )
        url = "https://www.freelancer.com/projects/sample"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("📄 Proposal", url=url),
             InlineKeyboardButton("🔗 Original", url=url)],
            [InlineKeyboardButton("⭐ Save", callback_data="job:save"),
             InlineKeyboardButton("🗑️ Delete", callback_data="job:delete")]])
        await update.effective_chat.send_message(job_text, parse_mode=ParseMode.HTML, reply_markup=kb)
        await asyncio.sleep(0.4)
        pph_text = (
            "<b>Logo Design for New Startup</b>\n<b>Budget:</b> 50.0–120.0 GBP (~$60–$145 USD)\n<b>Source:</b> PeoplePerHour\n<b>Match:</b> logo\n🎨 Create a modern, minimal logo for a UK startup. Provide vector files.\n"
        )
        pph_url = "https://www.peopleperhour.com/freelance-jobs/sample"
        pph_kb = InlineKeyboardMarkup([[InlineKeyboardButton("📄 Proposal", url=pph_url),
             InlineKeyboardButton("🔗 Original", url=pph_url)],
            [InlineKeyboardButton("⭐ Save", callback_data="job:save"),
             InlineKeyboardButton("🗑️ Delete", callback_data="job:delete")]])
        await update.effective_chat.send_message(pph_text, parse_mode=ParseMode.HTML, reply_markup=pph_kb)
        ensure_feed_events_schema()
        record_event("freelancer"); record_event("peopleperhour")
        await update.effective_chat.send_message("✅ Self-test OK — dummy events recorded.")
    except Exception as e:
        log.exception("selftest failed: %s", e)
        await update.effective_chat.send_message("⚠️ Self-test failed.")
# ---------- Saved ----------
async def saved_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show last saved jobs without overwriting main menu"""
    try:
        user_id = update.effective_user.id
        with get_session() as s:
            res = s.execute(text("""
                SELECT sj.job_id, sj.saved_at,
                       je.platform, je.title, je.description,
                       je.affiliate_url, je.original_url,
                       je.budget_amount, je.budget_currency,
                       je.budget_usd, je.created_at
                FROM saved_job sj
                LEFT JOIN job_event je ON je.id=sj.job_id
                WHERE sj.user_id=(SELECT id FROM "user" WHERE telegram_id=:tid)
                ORDER BY sj.saved_at DESC
                LIMIT 10
            """), {"tid": user_id}).fetchall()

        if not res:
            await update.effective_chat.send_message("💾 You have no saved jobs yet."); return

        lines = ["<b>💾 Your last saved jobs:</b>"]
        for r in res:
            title = r["title"] or "(no title)"
            platform = r["platform"] or "?"
            posted = r["created_at"].strftime("%Y-%m-%d %H:%M") if r["created_at"] else "?"
            budget = f"{r['budget_amount']} {r['budget_currency']}" if r["budget_amount"] and r["budget_currency"] else "N/A"
            usd = f" (~${r['budget_usd']:.2f})" if r["budget_usd"] else ""
            link = r["affiliate_url"] or r["original_url"] or ""
            lines.append(f"• <b>{title}</b>\n💰 {budget}{usd}\n🌍 {platform} | ⏱ {posted}\n🔗 <a href='{link}'>Open</a>")
        await update.effective_chat.send_message("\n\n".join(lines), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    except Exception as e:
        log.exception("saved_cmd failed: %s", e)
        await update.effective_chat.send_message("⚠️ Could not load saved jobs.")

# ---------- Contact ----------
async def contact_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(
        "📨 For support or extension, contact the admin:\n\n"
        "• Telegram: @Freelancer_Alert_Jobs_bot\n• Email: support@freelanceralerts.eu",
        disable_web_page_preview=True)

# ---------- Admin ----------
async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        await update.message.reply_text("Not allowed."); return
    with get_session() as s:
        rows = s.execute(text('SELECT telegram_id, username, is_active, is_blocked FROM "user" ORDER BY id DESC LIMIT 30')).fetchall()
    if not rows:
        await update.message.reply_text("No users."); return
    lines = [f"{r['telegram_id']} | @{r['username'] or '-'} | A:{r['is_active']} | B:{r['is_blocked']}" for r in rows]
    await update.message.reply_text("\n".join(lines))

# ---------- Menu / callbacks ----------
async def menu_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    await q.answer()
    if data == "act:addkw":
        await q.edit_message_text("Use /addkeyword <text> to add new keywords.")
    elif data == "act:settings":
        await mysettings_cmd(update, context)
    elif data == "act:help":
        await q.edit_message_text(HELP_EN + help_footer(STATS_WINDOW_HOURS), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    elif data == "act:saved":
        await saved_cmd(update, context)
    elif data == "act:contact":
        await contact_cmd(update, context)
    elif data == "act:admin":
        if is_admin_user(update.effective_user.id):
            await users_cmd(update, context)
        else:
            await q.edit_message_text("Not authorized.")
    else:
        await q.edit_message_text("❌ Unknown action.")

# ---------- Build ----------
def build_application() -> Application:
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", lambda u, c: u.message.reply_text(HELP_EN + help_footer(STATS_WINDOW_HOURS), parse_mode=ParseMode.HTML, disable_web_page_preview=True)))
    app.add_handler(CommandHandler("whoami", whoami_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))
    app.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app.add_handler(CommandHandler("delkeyword", delkeyword_cmd))
    app.add_handler(CommandHandler("clearkeywords", clearkeywords_cmd))
    app.add_handler(CommandHandler("selftest", selftest_cmd))
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CallbackQueryHandler(menu_action_cb, pattern=r"^act:"))

    return app
