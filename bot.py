# bot.py  — full replacement
import os
import logging
from datetime import datetime, timedelta
from typing import List

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ----- Project deps (exist already in your codebase) -----
from db import (
    ensure_schema,
    get_session,
    get_or_create_user_by_tid,
    list_user_keywords,
    add_user_keywords,
    User,
)
from config import ADMIN_IDS, TRIAL_DAYS, STATS_WINDOW_HOURS
from db_events import get_platform_stats  # created in the patch we added

log = logging.getLogger("bot")

# Read token (keeps your existing env naming)
TELEGRAM_BOT_TOKEN = (
    os.getenv("TELEGRAM_BOT_TOKEN")
    or os.getenv("BOT_TOKEN")
    or os.getenv("TELEGRAM_TOKEN")
)
if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN env var is required")


# =========================================================
#                         UI
# =========================================================
def main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    """
    Matches the screenshots:
    ➕ Add Keywords | ⚙️ Settings
    🆘 Help        | 💾 Saved
    📨 Contact
    (+ 🔥 Admin row for admins)
    """
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


def welcome_full(trial_days: int) -> str:
    return (
        "<b>👋 Welcome to Freelancer Alert Bot!</b>\n\n"
        f"🎁 You have a <b>{trial_days}-day free trial</b>.\n"
        "Automatically finds matching freelance jobs from top platforms and sends you instant alerts.\n\n"
        "Use <code>/help</code> to see how it works.\n"
    )


def features_block() -> str:
    return (
        "<b>✨ Features</b>\n"
        "• Realtime job alerts (Freelancer API)\n"
        "• Affiliate-wrapped <b>Proposal</b> & <b>Original</b> links\n"
        "• Budget shown + USD conversion\n"
        "• ⭐ Keep / 🗑 Delete buttons\n"
        "• 10-day free trial, extend via admin\n"
        "• Multi-keyword search (single/all modes)\n"
        "• Platforms by country (incl. GR boards)\n"
    )


HELP_EN = (
    "<b>🧭 Help / How it works</b>\n\n"
    "<b>1)</b> Add keywords with <code>/addkeyword</code> <i>python, telegram</i> (comma-separated, English or Greek).\n"
    "<b>2)</b> Set your countries with <code>/setcountry</code> <i>US,UK</i> (or <i>ALL</i>).\n"
    "<b>3)</b> Save a proposal template with <code>/setproposal &lt;text&gt;</code> —\n"
    "placeholders: <code>{jobtitle}</code>, <code>{experience}</code>, <code>{stack}</code>, "
    "<code>{availability}</code>, <code>{step1}</code>, <code>{step2}</code>, <code>{step3}</code>, "
    "<code>{budgettime}</code>, <code>{portfolio}</code>, <code>{name}</code>.\n"
    "<b>4)</b> When a job arrives you can: keep, delete, open <b>Proposal</b> or <b>Original</b> link.\n\n"
    "<b>Use</b> <code>/mysettings</code> anytime. Try <code>/selftest</code> for a sample.\n"
    "<b>/platforms</b> <i>CC</i> to see platforms by country (e.g., <code>/platforms GR</code>).\n"
)


def help_footer(hours: int) -> str:
    return (
        "\n<b>🛰 Platforms monitored:</b>\n"
        "• Global: <a href=\"https://www.freelancer.com\">Freelancer.com</a> (affiliate links), "
        "PeoplePerHour, Malt, Workana, Guru, 99designs, Toptal*, Codeable*, YunoJuno*, Worksome*, twago, freelancermap\n"
        "  <i>(* referral/curated platforms)</i>\n"
        "• Greece: <a href=\"https://www.jobfind.gr\">JobFind.gr</a>, "
        "<a href=\"https://www.skywalker.gr\">Skywalker.gr</a>, <a href=\"https://www.kariera.gr\">Kariera.gr</a>\n\n"
        "<b>👑 Admin commands</b>:\n"
        "<code>/users</code> — list users\n"
        "<code>/grant &lt;telegram_id&gt; &lt;days&gt;</code> — extend license\n"
        "<code>/block &lt;telegram_id&gt;</code> / <code>/unblock &lt;telegram_id&gt;</code>\n"
        "<code>/broadcast &lt;text&gt;</code> — to all active\n"
        f"<code>/feedstatus</code> — last {hours}h by platform\n"
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
        "  <i>(* referral/curated platforms)</i>\n"
        "• Greece: <a href=\"https://www.jobfind.gr\">JobFind.gr</a>, "
        "<a href=\"https://www.skywalker.gr\">Skywalker.gr</a>, <a href=\"https://www.kariera.gr\">Kariera.gr</a>\n\n"
        "<i>For extension, contact the admin.</i>"
    )


# =========================================================
#                    Command Handlers
# =========================================================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Create user if missing
    with get_session() as db:
        u = get_or_create_user_by_tid(db, update.effective_user.id)
        kws = list_user_keywords(db, u.id)

    is_admin = update.effective_user.id in ADMIN_IDS

    # Welcome header + features + main menu (as screenshots)
    await update.effective_chat.send_message(
        welcome_full(trial_days=TRIAL_DAYS),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_kb(is_admin=is_admin),
    )
    await update.effective_chat.send_message(features_block(), parse_mode=ParseMode.HTML)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(
        HELP_EN + help_footer(STATS_WINDOW_HOURS), parse_mode=ParseMode.HTML
    )


async def addkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Prompt if no args
    if not context.args:
        await update.message.reply_text(
            "Δώσε λέξεις-κλειδιά χωρισμένες με κόμμα. Παράδειγμα:\n"
            "<code>/addkeyword logo, lighting</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    raw = " ".join(context.args)
    parts = [p.strip() for p in raw.split(",")]
    parts = [p for p in parts if p]

    with get_session() as db:
        u = get_or_create_user_by_tid(db, update.effective_user.id)
        inserted = add_user_keywords(db, u.id, parts)
        kws = list_user_keywords(db, u.id)

    msg = f"✅ Προστέθηκαν {inserted} νέες λέξεις.\n\n"
    msg += "Τρέχουσες λέξεις-κλειδιά:\n• " + (", ".join(kws) if kws else "—")
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as db:
        u = get_or_create_user_by_tid(db, update.effective_user.id)
        kws = list_user_keywords(db, u.id)
        # Optional fields may exist in your DB model
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
    )


# =========================================================
#                    Admin Handlers
# =========================================================
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
    tg_id = int(context.args[0])
    days = int(context.args[1])
    until = datetime.utcnow() + timedelta(days=days)
    with get_session() as db:
        u = db.query(User).filter(User.telegram_id == tg_id).first()
        if not u:
            await update.effective_chat.send_message("User not found.")
            return
        setattr(u, "license_until", until)
        db.commit()
    await update.effective_chat.send_message(
        f"✅ Granted license to {tg_id} until {until.isoformat()}",
        parse_mode=ParseMode.HTML,
    )


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
    await update.effective_chat.send_message(f"⛔ Blocked {tg_id}")


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
    await update.effective_chat.send_message(f"✅ Unblocked {tg_id}")


async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.effective_chat.send_message("Usage: /broadcast <text>")
        return
    text = " ".join(context.args)
    # send to active & not blocked users
    with get_session() as db:
        users = db.query(User).filter(
            getattr(User, "is_active") == True,  # noqa: E712
            getattr(User, "is_blocked") == False,  # noqa: E712
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
        await update.effective_chat.send_message(f"No events in last {STATS_WINDOW_HOURS}h.")
        return
    lines = [f"📊 Feed status (last {STATS_WINDOW_HOURS}h):"]
    for src, cnt in stats.items():
        lines.append(f"• {src}: {cnt}")
    await update.effective_chat.send_message("\n".join(lines))


# =========================================================
#                    Menu Callbacks
# =========================================================
async def menu_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data or ""

    if data == "act:addkw":
        await q.message.reply_text(
            "Add keywords (comma-separated). Example:\n<code>/addkeyword logo, lighting</code>",
            parse_mode=ParseMode.HTML,
        )
        await q.answer()
        return

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
        await q.message.reply_text(text, parse_mode=ParseMode.HTML)
        await q.answer()
        return

    if data == "act:help":
        await q.message.reply_text(HELP_EN + help_footer(STATS_WINDOW_HOURS), parse_mode=ParseMode.HTML)
        await q.answer()
        return

    if data == "act:saved":
        await q.message.reply_text("💾 Saved — (coming soon)")
        await q.answer()
        return

    if data == "act:contact":
        await q.message.reply_text("📨 Contact admin via this chat or /users (admin only) to get your ID.")
        await q.answer()
        return

    if data == "act:admin":
        if not _is_admin(q.from_user.id):
            await q.answer("Not allowed", show_alert=True)
            return
        await q.message.reply_text(
            "<b>Admin panel</b>\n"
            "/users — list users\n"
            "/grant <id> <days> — extend license\n"
            "/block <id> / /unblock <id>\n"
            "/broadcast <text>\n"
            "/feedstatus — last hours by platform",
            parse_mode=ParseMode.HTML,
        )
        await q.answer()
        return

    await q.answer()


# =========================================================
#                    Application Factory
# =========================================================
def build_application() -> Application:
    ensure_schema()
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Public commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))

    # Admin commands
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CommandHandler("grant", grant_cmd))
    app.add_handler(CommandHandler("block", block_cmd))
    app.add_handler(CommandHandler("unblock", unblock_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("feedstatus", feedstatus_cmd))

    # Menu callbacks
    app.add_handler(CallbackQueryHandler(menu_action_cb, pattern=r"^act:(addkw|settings|help|saved|contact|admin)$"))

    log.info("Handlers ready: /start /help /addkeyword /mysettings + admin + menu callbacks")
    return app
