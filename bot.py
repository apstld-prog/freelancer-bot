# bot.py — full replacement (English-only UX + code)
import os
import logging
from datetime import datetime, timedelta
from typing import List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ---- Project-local modules (already present in your repo) ----
from db import (
    ensure_schema,
    get_session,
    get_or_create_user_by_tid,
    list_user_keywords,
    add_user_keywords,     # may accept List[str] or comma string (handled below)
    User,
    # Optional: remove_user_keyword may or may not exist
)
from config import ADMIN_IDS, TRIAL_DAYS, STATS_WINDOW_HOURS
from db_events import get_platform_stats  # persistent per-platform stats

log = logging.getLogger("bot")

TELEGRAM_BOT_TOKEN = (
    os.getenv("TELEGRAM_BOT_TOKEN")
    or os.getenv("BOT_TOKEN")
    or os.getenv("TELEGRAM_TOKEN")
)
if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN env var is required")


# ======================================================================
# UI (English text)
# ======================================================================
def main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    row1 = [
        InlineKeyboardButton("➕ Add Keywords", callback_data="act:addkw"),
        InlineKeyboardButton("⚙️ Settings", callback_data="act:settings"),
    ]
    row2 = [
        InlineKeyboardButton("🆘 Help", callback_data="act:help"),
        InlineKeyboardButton("💾 Saved", callback_data="act:saved"),
    ]
    row3 = [InlineKeyboardButton("📨 Contact", callback_data="act:contact")]
    kb = [row1, row2, row3]
    if is_admin:
        kb.append([InlineKeyboardButton("🔥 Admin", callback_data="act:admin")])
    return InlineKeyboardMarkup(kb)


def welcome_text(trial_days: int) -> str:
    return (
        "<b>👋 Welcome to Freelancer Alert Bot!</b>\n\n"
        f"🎁 You have a <b>{trial_days}-day free trial</b>.\n"
        "The bot finds matching freelance jobs from top platforms and sends instant alerts.\n\n"
        "Use <code>/help</code> for instructions.\n"
    )


def features_text() -> str:
    return (
        "<b>✨ Features</b>\n"
        "• Real-time job alerts (Freelancer API)\n"
        "• Affiliate-wrapped <b>Proposal</b> & <b>Original</b> links\n"
        "• Budget shown + USD conversion\n"
        "• ⭐ Keep / 🗑 Delete\n"
        "• 10-day free trial (extend via admin)\n"
        "• Multi-keyword search\n"
        "• Platforms by country (incl. GR boards)\n"
    )


HELP_EN = (
    "<b>🧭 Help / How it works</b>\n\n"
    "<b>1)</b> Add keywords with <code>/addkeyword</code>, e.g. <i>python, telegram</i> (comma-separated).\n"
    "<b>2)</b> Set countries with <code>/setcountry</code> (e.g. <i>US,UK</i> or <i>ALL</i>).\n"
    "<b>3)</b> Save a proposal template using <code>/setproposal &lt;text&gt;</code> — "
    "placeholders: <code>{jobtitle}</code>, <code>{experience}</code>, <code>{stack}</code>, "
    "<code>{availability}</code>, <code>{step1}</code>, <code>{step2}</code>, <code>{step3}</code>, "
    "<code>{budgettime}</code>, <code>{portfolio}</code>, <code>{name}</code>.\n"
    "<b>4)</b> When a job arrives you can: keep it, delete it, open the <b>Proposal</b> or <b>Original</b> link.\n\n"
    "<b>Use</b> <code>/mysettings</code> anytime. Try <code>/selftest</code> for a sample card.\n"
    "<b>/platforms</b> CC shows platforms by country (e.g., <code>/platforms GR</code>).\n"
)


def help_footer(hours: int) -> str:
    return (
        "\n<b>🛰 Platforms monitored:</b>\n"
        "• Global: <a href=\"https://www.freelancer.com\">Freelancer.com</a> (affiliate links), "
        "PeoplePerHour, Malt, Workana, Guru, 99designs, Toptal*, Codeable*, YunoJuno*, Worksome*, twago, freelancermap\n"
        "  <i>(* referral/curated)</i>\n"
        "• Greece: <a href=\"https://www.jobfind.gr\">JobFind.gr</a>, "
        "<a href=\"https://www.skywalker.gr\">Skywalker.gr</a>, <a href=\"https://www.kariera.gr\">Kariera.gr</a>\n\n"
        "<b>👑 Admin commands</b>:\n"
        "<code>/users</code>, <code>/grant &lt;id&gt; &lt;days&gt;</code>, "
        "<code>/block &lt;id&gt;</code>/<code>/unblock &lt;id&gt;</code>, "
        "<code>/broadcast &lt;text&gt;</code>, <code>/feedstatus</code>\n"
        "<i>Link previews disabled for clean help.</i>\n"
    )


def settings_text(
    keywords: List[str],
    countries: str | None,
    proposal_template: str | None,
    trial_start,
    trial_end,
    license_until,
    active: bool,
    blocked: bool,
) -> str:
    def b(v: bool) -> str:
        return "✅" if v else "❌"

    k = ", ".join(keywords) if keywords else "(none)"
    c = countries if countries else "ALL"
    pt = "(none)" if not proposal_template else "(saved)"
    ts = trial_start.isoformat().replace("+00:00", "Z") if trial_start else "—"
    te = trial_end.isoformat().replace("+00:00", "Z") if trial_end else "—"
    lic = "None" if not license_until else license_until.isoformat().replace("+00:00", "Z")

    return (
        "<b>🛠 Your Settings</b>\n"
        f"• <b>Keywords:</b> {k}\n"
        f"• <b>Countries:</b> {c}\n"
        f"• <b>Proposal template:</b> {pt}\n\n"
        f"<b>●</b> Start date: {ts}\n"
        f"<b>●</b> Trial ends: {te} UTC\n"
        f"<b>🔑</b> License until: {lic}\n"
        f"<b>✅ Active:</b> {b(active)}    <b>⛔ Blocked:</b> {b(blocked)}\n\n"
        "<b>🛰 Platforms monitored:</b>\n"
        "• Global: <a href=\"https://www.freelancer.com\">Freelancer.com</a> (affiliate links), PeoplePerHour, "
        "Malt, Workana, Guru, 99designs, Toptal*, Codeable*, YunoJuno*, Worksome*, twago, freelancermap\n"
        "  <i>(* referral/curated)</i>\n"
        "• Greece: <a href=\"https://www.jobfind.gr\">JobFind.gr</a>, "
        "<a href=\"https://www.skywalker.gr\">Skywalker.gr</a>, <a href=\"https://www.kariera.gr\">Kariera.gr</a>\n\n"
        "<i>For extension, contact the admin.</i>"
    )


# ======================================================================
# Keyword helpers (robust to unknown add_user_keywords signature)
# ======================================================================
def parse_keywords_input(raw: str) -> List[str]:
    # Accept comma- and/or space-separated input
    parts = [p.strip() for chunk in raw.split(",") for p in chunk.split() if p.strip()]
    # De-duplicate case-insensitively
    seen, clean = set(), []
    for p in parts:
        k = p.lower()
        if k not in seen:
            seen.add(k)
            clean.append(p)
    return clean


def add_keywords_safe(db_session, user_id: int, keywords: List[str]) -> int:
    if not keywords:
        return 0
    inserted = 0
    try:
        res = add_user_keywords(db_session, user_id, keywords)  # try list signature
        inserted = int(res) if res is not None else 0
        if inserted == 0:
            current = list_user_keywords(db_session, user_id) or []
            new_set = set([*current, *keywords])
            inserted = max(0, len(new_set) - len(current))
    except TypeError:
        try:
            res = add_user_keywords(db_session, user_id, ", ".join(keywords))  # fallback string signature
            inserted = int(res) if res is not None else 0
            if inserted == 0:
                current = list_user_keywords(db_session, user_id) or []
                new_set = set([*current, *keywords])
                inserted = max(0, len(new_set) - len(current))
        except Exception:
            inserted = 0
    return inserted


def remove_keyword_safe(db_session, user_id: int, keyword: str) -> bool:
    try:
        from db import remove_user_keyword  # optional helper
        before = list_user_keywords(db_session, user_id) or []
        if keyword in before:
            remove_user_keyword(db_session, user_id, keyword)  # type: ignore
            after = list_user_keywords(db_session, user_id) or []
            return keyword not in after
        return False
    except Exception:
        return False


# ======================================================================
# Public commands (English text)
# ======================================================================
async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Your Telegram ID: <code>{update.effective_user.id}</code>",
        parse_mode=ParseMode.HTML,
    )


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as db:
        u = get_or_create_user_by_tid(db, update.effective_user.id)
        _ = list_user_keywords(db, u.id)
    is_admin = update.effective_user.id in ADMIN_IDS
    await update.effective_chat.send_message(
        welcome_text(trial_days=TRIAL_DAYS),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_kb(is_admin=is_admin),
    )
    await update.effective_chat.send_message(features_text(), parse_mode=ParseMode.HTML)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(
        HELP_EN + help_footer(STATS_WINDOW_HOURS),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def addkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Add keywords separated by commas. Example:\n"
            "<code>/addkeyword logo, lighting</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    raw = " ".join(context.args)
    keywords = parse_keywords_input(raw)
    if not keywords:
        await update.message.reply_text("No valid keywords were provided.", parse_mode=ParseMode.HTML)
        return
    with get_session() as db:
        u = get_or_create_user_by_tid(db, update.effective_user.id)
        inserted = add_keywords_safe(db, u.id, keywords)
        current = list_user_keywords(db, u.id) or []
    msg = f"✅ Added {inserted} new keyword(s).\n\nCurrent keywords:\n• " + (", ".join(current) if current else "—")
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


async def keywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as db:
        u = get_or_create_user_by_tid(db, update.effective_user.id)
        current = list_user_keywords(db, u.id) or []
    text = (
        "<b>Keywords</b>\n"
        "• " + (", ".join(current) if current else "—") + "\n\n"
        "Add with <code>/addkeyword logo, lighting</code>\n"
        "Remove with <code>/delkeyword logo</code>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def delkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: <code>/delkeyword &lt;word&gt;</code>", parse_mode=ParseMode.HTML)
        return
    kw = " ".join(context.args).strip()
    with get_session() as db:
        u = get_or_create_user_by_tid(db, update.effective_user.id)
        ok = remove_keyword_safe(db, u.id, kw)
        current = list_user_keywords(db, u.id) or []
    if ok:
        await update.message.reply_text(
            f"🗑 Removed <b>{kw}</b>.\nCurrent: " + (", ".join(current) if current else "—"),
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(
            "Could not remove it automatically. "
            "You can manage the list by adding new ones with /addkeyword.",
            parse_mode=ParseMode.HTML,
        )


async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as db:
        u = get_or_create_user_by_tid(db, update.effective_user.id)
        kws = list_user_keywords(db, u.id)
        trial_start = getattr(u, "trial_start", None)
        trial_end = getattr(u, "trial_end", None)
        license_until = getattr(u, "license_until", None)
    await update.message.reply_text(
        settings_text(
            keywords=kws,
            countries=getattr(u, "countries", "ALL"),
            proposal_template=getattr(u, "proposal_template", None),
            trial_start=trial_start,
            trial_end=trial_end,
            license_until=license_until,
            active=bool(getattr(u, "is_active", True)),
            blocked=bool(getattr(u, "is_blocked", False)),
        ),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def selftest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    job_text = (
        "<b>Email Signature from Existing Logo</b>\n"
        "<b>Budget:</b> 10.0–30.0 USD\n"
        "<b>Source:</b> Freelancer\n"
        "<b>Match:</b> logo\n"
        "✏️ Please create an editable version of the email signature based on the provided logo.\n"
    )
    proposal_url = "https://www.freelancer.com/get/apstld?f=give&dl=https://www.freelancer.com/projects/sample"
    original_url = proposal_url
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📄 Proposal", url=proposal_url), InlineKeyboardButton("🔗 Original", url=original_url)],
            [InlineKeyboardButton("⭐ Save", callback_data="job:save"), InlineKeyboardButton("🗑️ Delete", callback_data="job:delete")],
        ]
    )
    await update.effective_chat.send_message(job_text, parse_mode=ParseMode.HTML, reply_markup=kb)


# ======================================================================
# Admin
# ======================================================================
def _is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return
    with get_session() as db:
        rows = db.query(User).order_by(User.id.desc()).limit(100).all()
    lines = ["<b>Users</b>"]
    for u in rows:
        kw_count = len(u.keywords or [])
        trial = getattr(u, "trial_end", None)
        lic = getattr(u, "license_until", None)
        active = "✅" if getattr(u, "is_active", True) else "❌"
        blocked = "✅" if getattr(u, "is_blocked", False) else "❌"
        lines.append(
            f"• <a href=\"tg://user?id={u.telegram_id}\">{u.telegram_id}</a> — "
            f"kw:{kw_count} | trial:{trial} | lic:{lic} | A:{active} B:{blocked}"
        )
    await update.effective_chat.send_message("\n".join(lines), parse_mode=ParseMode.HTML)


async def grant_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return
    if len(context.args) < 2:
        await update.effective_chat.send_message("Usage: /grant <telegram_id> <days>")
        return
    tg_id = int(context.args[0]); days = int(context.args[1])
    until = datetime.utcnow() + timedelta(days=days)
    with get_session() as db:
        u = db.query(User).filter(User.telegram_id == tg_id).first()
        if not u:
            await update.effective_chat.send_message("User not found.")
            return
        setattr(u, "license_until", until)
        db.commit()
    await update.effective_chat.send_message(f"✅ Granted until {until.isoformat()} for {tg_id}.")


async def block_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.effective_chat.send_message("Usage: /block <telegram_id>")
        return
    tg_id = int(context.args[0])
    with get_session() as db:
        u = db.query(User).filter(User.telegram_id == tg_id).first()
        if not u:
            await update.effective_chat.send_message("User not found.")
            return
        setattr(u, "is_blocked", True)
        db.commit()
    await update.effective_chat.send_message(f"⛔ Blocked {tg_id}.")


async def unblock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.effective_chat.send_message("Usage: /unblock <telegram_id>")
        return
    tg_id = int(context.args[0])
    with get_session() as db:
        u = db.query(User).filter(User.telegram_id == tg_id).first()
        if not u:
            await update.effective_chat.send_message("User not found.")
            return
        setattr(u, "is_blocked", False)
        db.commit()
    await update.effective_chat.send_message(f"✅ Unblocked {tg_id}.")


async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.effective_chat.send_message("Usage: /broadcast <text>")
        return
    text = " ".join(context.args)
    with get_session() as db:
        users = db.query(User).filter(
            getattr(User, "is_active") == True,   # noqa: E712
            getattr(User, "is_blocked") == False  # noqa: E712
        ).all()
    sent = 0
    for u in users:
        try:
            await context.bot.send_message(chat_id=u.telegram_id, text=text, parse_mode=ParseMode.HTML)
            sent += 1
        except Exception:
            pass
    await update.effective_chat.send_message(f"📣 Broadcast sent to {sent} users.")


async def feedstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return
    stats = get_platform_stats(STATS_WINDOW_HOURS)
    if not stats:
        await update.effective_chat.send_message(f"No events in the last {STATS_WINDOW_HOURS} hours.")
        return
    lines = [f"📊 Feed status (last {STATS_WINDOW_HOURS}h):"]
    for src, cnt in stats.items():
        lines.append(f"• {src}: {cnt}")
    await update.effective_chat.send_message("\n".join(lines))


# ======================================================================
# Menu callbacks
# ======================================================================
async def menu_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = (q.data or "").strip()

    if data == "act:addkw":
        await q.message.reply_text(
            "Add keywords (comma-separated). Example:\n"
            "<code>/addkeyword logo, lighting</code>",
            parse_mode=ParseMode.HTML,
        )
        await q.answer(); return

    if data == "act:settings":
        with get_session() as db:
            u = get_or_create_user_by_tid(db, q.from_user.id)
            kws = list_user_keywords(db, u.id)
        text = settings_text(
            keywords=kws,
            countries=getattr(u, "countries", "ALL"),
            proposal_template=getattr(u, "proposal_template", None),
            trial_start=getattr(u, "trial_start", None),
            trial_end=getattr(u, "trial_end", None),
            license_until=getattr(u, "license_until", None),
            active=bool(getattr(u, "is_active", True)),
            blocked=bool(getattr(u, "is_blocked", False)),
        )
        await q.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        await q.answer(); return

    if data == "act:help":
        await q.message.reply_text(HELP_EN + help_footer(STATS_WINDOW_HOURS),
                                   parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        await q.answer(); return

    if data == "act:saved":
        await q.message.reply_text("💾 Saved (coming soon).")
        await q.answer(); return

    if data == "act:contact":
        await q.message.reply_text("📨 Send a message here to contact the admin.")
        await q.answer(); return

    if data == "act:admin":
        if q.from_user.id not in ADMIN_IDS:
            await q.answer("Not allowed", show_alert=True); return
        await q.message.reply_text(
            "<b>Admin panel</b>\n"
            "/users — list users\n"
            "/grant <id> <days> — license\n"
            "/block <id> / /unblock <id>\n"
            "/broadcast <text>\n"
            "/feedstatus — per-platform stats",
            parse_mode=ParseMode.HTML,
        )
        await q.answer(); return

    await q.answer()


# ======================================================================
# Application factory
# ======================================================================
def build_application() -> Application:
    ensure_schema()
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Public commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("whoami", whoami_cmd))
    app.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app.add_handler(CommandHandler("keywords", keywords_cmd))
    app.add_handler(CommandHandler("delkeyword", delkeyword_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))
    app.add_handler(CommandHandler("selftest", selftest_cmd))

    # Admin commands
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CommandHandler("grant", grant_cmd))
    app.add_handler(CommandHandler("block", block_cmd))
    app.add_handler(CommandHandler("unblock", unblock_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("feedstatus", feedstatus_cmd))

    # Menu callbacks
    app.add_handler(CallbackQueryHandler(
        menu_action_cb, pattern=r"^act:(addkw|settings|help|saved|contact|admin)$"
    ))

    log.info("Handlers ready: /start /help /whoami /addkeyword /keywords /delkeyword /mysettings /selftest + admin + menu callbacks")
    return app
