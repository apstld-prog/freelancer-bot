# =========================================================
# Freelancer Alert Bot — Final Restored Edition (Full UI)
# =========================================================
import os, logging, asyncio, re
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, Application, CommandHandler,
    CallbackQueryHandler, MessageHandler, ContextTypes, filters,
)
from sqlalchemy import text
from db import get_session, get_or_create_user_by_tid, ensure_schema
from db_keywords import list_keywords, add_keywords, delete_keywords, clear_keywords, count_keywords
from db_events import ensure_feed_events_schema, record_event, get_platform_stats
from config import ADMIN_IDS, TRIAL_DAYS, STATS_WINDOW_HOURS

# =========================================================
# Logging setup
# =========================================================
log = logging.getLogger("bot")
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = (
    os.getenv("TELEGRAM_BOT_TOKEN")
    or os.getenv("BOT_TOKEN")
    or os.getenv("TELEGRAM_TOKEN")
)
if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN env var is required")

# =========================================================
# Helpers
# =========================================================
def is_admin_user(tid: int) -> bool:
    try:
        return tid in set(int(x) for x in (ADMIN_IDS or []))
    except Exception:
        return False

def all_admin_ids() -> set[int]:
    return set(int(x) for x in (ADMIN_IDS or []))

FX = {"EUR": 1.08, "GBP": 1.27, "AUD": 0.65, "CAD": 0.73, "USD": 1.0}
def to_usd(amount: float, cur: str) -> str:
    if not amount or not cur:
        return ""
    rate = FX.get(cur.upper(), 1)
    if rate == 1:
        return f"{amount:.2f} USD"
    return f"{amount:.2f} {cur.upper()} (~${amount*rate:.2f} USD)"

# =========================================================
# UI Components
# =========================================================
def main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    kb = [
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
        kb.append([InlineKeyboardButton("🔥 Admin", callback_data="act:admin")])
    return InlineKeyboardMarkup(kb)

def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("👥 Users", callback_data="adm:users"),
                InlineKeyboardButton("📊 Feed Status", callback_data="adm:feedstatus"),
            ],
            [
                InlineKeyboardButton("📢 Broadcast", callback_data="adm:broadcast"),
                InlineKeyboardButton("🗝 Grant License", callback_data="adm:grant"),
            ],
            [
                InlineKeyboardButton("🚫 Block / ✅ Unblock", callback_data="adm:block"),
                InlineKeyboardButton("⬅️ Back", callback_data="act:main"),
            ],
        ]
    )

HELP_TEXT = (
    "<b>🧭 Help / How it works</b>\n\n"
    "• Add keywords: <code>/addkeyword logo, lighting, sales</code>\n"
    "• Delete keywords: <code>/delkeyword logo</code>\n"
    "• Clear all: <code>/clearkeywords</code>\n\n"
    "• Set countries: <code>/setcountry US,UK</code>\n"
    "• Save proposal: <code>/setproposal your text</code>\n"
    "• Self-test jobs: <code>/selftest</code>\n"
    "• View settings: <code>/mysettings</code>\n\n"
    "<b>🛰 Platforms monitored:</b>\n"
    "Freelancer, PeoplePerHour, Malt, Workana, Guru, 99designs, YunoJuno, Worksome, twago, freelancermap\n"
    "Greek boards: Skywalker.gr, JobFind.gr, Kariera.gr\n\n"
    "<b>👑 Admin Commands:</b>\n"
    "<code>/users</code> <code>/grant &lt;id&gt; &lt;days&gt;</code> "
    "<code>/block &lt;id&gt;</code> <code>/unblock &lt;id&gt;</code>\n"
    "<code>/broadcast &lt;text&gt;</code> <code>/feedstatus</code>\n"
)

def welcome_text(expiry: Optional[datetime]) -> str:
    extra = (
        f"\n<b>🎁 Free trial ends:</b> {expiry.strftime('%Y-%m-%d %H:%M UTC')}"
        if expiry
        else ""
    )
    return (
        "<b>👋 Welcome to Freelancer Alert Bot!</b>\n\n"
        "🚀 Receive instant job alerts from top freelance platforms based on your keywords."
        f"{extra}\n\n"
        "Use <code>/help</code> to learn how to customize your alerts.\n"
    )

def settings_text(
    keywords: List[str],
    countries: Optional[str],
    proposal_template: Optional[str],
    trial_start: Optional[datetime],
    trial_end: Optional[datetime],
    license_until: Optional[datetime],
    active: bool,
    blocked: bool,
) -> str:
    def b(v: bool) -> str:
        return "✅" if v else "❌"

    kws = ", ".join(keywords) if keywords else "(none)"
    c = countries if countries else "ALL"
    pt = "(none)" if not proposal_template else "(saved)"
    ts = trial_start.strftime("%Y-%m-%d %H:%M") if trial_start else "—"
    te = trial_end.strftime("%Y-%m-%d %H:%M") if trial_end else "—"
    lic = license_until.strftime("%Y-%m-%d %H:%M") if license_until else "None"

    return (
        "<b>🛠 Your Settings</b>\n"
        f"• <b>Keywords:</b> {kws}\n"
        f"• <b>Countries:</b> {c}\n"
        f"• <b>Proposal Template:</b> {pt}\n\n"
        f"<b>●</b> Start Date: {ts}\n"
        f"<b>●</b> Trial Ends: {te} UTC\n"
        f"<b>🔑</b> License Until: {lic}\n"
        f"<b>✅ Active:</b> {b(active)}    <b>⛔ Blocked:</b> {b(blocked)}\n\n"
        "<b>🛰 Platforms Monitored:</b> Global + Greek boards.\n"
        "<i>For extension, contact admin via /contact.</i>"
    )

# =========================================================
# /start + /help + /mysettings
# =========================================================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        s.execute(
            text(
                'UPDATE "user" SET trial_start=COALESCE(trial_start,NOW()), '
                'trial_end=COALESCE(trial_end,NOW()+make_interval(days=>:d)) WHERE id=:id'
            ),
            {"id": u.id, "d": TRIAL_DAYS},
        )
        expiry = s.execute(
            text('SELECT COALESCE(license_until, trial_end) AS exp FROM "user" WHERE id=:id'),
            {"id": u.id},
        ).fetchone()["exp"]
        s.commit()
    await update.effective_chat.send_message(
        welcome_text(expiry),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_kb(is_admin=is_admin_user(update.effective_user.id)),
    )
    await update.effective_chat.send_message(
        HELP_TEXT,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(
        HELP_TEXT, parse_mode=ParseMode.HTML, disable_web_page_preview=True
    )

async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        kws = list_keywords(u.id)
        row = s.execute(
            text(
                'SELECT countries, proposal_template, trial_start, trial_end, license_until, is_active, is_blocked '
                'FROM "user" WHERE id=:id'
            ),
            {"id": u.id},
        ).fetchone()
    await update.message.reply_text(
        settings_text(
            kws,
            row["countries"],
            row["proposal_template"],
            row["trial_start"],
            row["trial_end"],
            row["license_until"],
            bool(row["is_active"]),
            bool(row["is_blocked"]),
        ),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
# =========================================================
# Keyword Management
# =========================================================
def _parse_keywords(raw: str) -> List[str]:
    parts = [p.strip() for chunk in raw.split(",") for p in chunk.split() if p.strip()]
    seen, out = set(), []
    for p in parts:
        if p.lower() not in seen:
            seen.add(p.lower())
            out.append(p)
    return out

async def addkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Add keywords separated by commas.\nExample: <code>/addkeyword logo, lighting</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    kws = _parse_keywords(" ".join(context.args))
    if not kws:
        await update.message.reply_text("No valid keywords provided.")
        return
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        add_keywords(u.id, kws)
    await update.message.reply_text("✅ Keywords added successfully.")

async def delkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Delete keywords.\nExample: <code>/delkeyword logo</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    kws = _parse_keywords(" ".join(context.args))
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        delete_keywords(u.id, kws)
    await update.message.reply_text("🗑 Selected keywords deleted.")

async def clearkeywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        clear_keywords(u.id)
    await update.message.reply_text("✅ All keywords cleared.")

# =========================================================
# Selftest (Full Restored)
# =========================================================
async def selftest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_feed_events_schema()
    now = datetime.utcnow()
    jobs = [
        {
            "platform": "Freelancer",
            "title": "Design a Modern Company Logo",
            "budget_amount": 50,
            "budget_currency": "EUR",
            "match": "logo",
            "affiliate_url": "https://www.freelancer.com/projects/sample",
        },
        {
            "platform": "PeoplePerHour",
            "title": "Landing Page Development (WordPress)",
            "budget_amount": 120,
            "budget_currency": "USD",
            "match": "wordpress",
            "affiliate_url": "https://www.peopleperhour.com/freelance-jobs/sample",
        },
    ]

    for j in jobs:
        record_event(
            j["platform"],
            j["title"],
            j["title"],
            j["affiliate_url"],
            j["affiliate_url"],
            j["budget_amount"],
            j["budget_currency"],
            j["budget_amount"],
            now,
            f"{j['platform']}-{j['title']}",
        )

    for j in jobs:
        msg = (
            f"<b>{j['title']}</b>\n"
            f"<b>Budget:</b> {to_usd(j['budget_amount'], j['budget_currency'])}\n"
            f"<b>Source:</b> {j['platform']}\n"
            f"<b>Match:</b> {j['match']}\n\n"
            f"🕓 Posted: {now.strftime('%Y-%m-%d %H:%M UTC')}"
        )
        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("📄 Proposal", url=j["affiliate_url"]),
                    InlineKeyboardButton("🔗 Original", url=j["affiliate_url"]),
                ],
                [
                    InlineKeyboardButton("⭐ Save", callback_data=f"job:save:{j['platform']}"),
                    InlineKeyboardButton("🗑️ Delete", callback_data=f"job:delete:{j['platform']}"),
                ],
            ]
        )
        await update.effective_chat.send_message(msg, parse_mode=ParseMode.HTML, reply_markup=kb)
        await asyncio.sleep(0.5)

    await update.effective_chat.send_message("✅ Self-test completed with 2 demo jobs.")
    log.info("Self-test OK: demo jobs sent.")

# =========================================================
# Contact / Chat Between User & Admin
# =========================================================
active_contact = {}

async def contact_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    active_contact[uid] = True
    await update.effective_chat.send_message(
        "📩 Please type your message for the admin.\nType /cancel to exit contact mode.",
        parse_mode=ParseMode.HTML,
    )

async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in active_contact:
        active_contact.pop(uid)
    await update.message.reply_text("❌ Contact session ended.")

async def message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    txt = update.message.text
    if not txt:
        return

    # Admin replying to user
    if is_admin_user(uid) and txt.startswith("/reply"):
        parts = txt.split(maxsplit=2)
        if len(parts) < 3:
            await update.message.reply_text("Usage: /reply <user_id> <message>")
            return
        to_id = int(parts[1])
        msg = parts[2]
        await context.bot.send_message(
            to_id, f"💬 <b>Admin:</b> {msg}", parse_mode=ParseMode.HTML
        )
        await update.message.reply_text("✅ Reply sent.")
        return

    # User message → forward to admins
    if active_contact.get(uid):
        for admin in all_admin_ids():
            kb = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("💬 Reply", callback_data=f"reply:{uid}"),
                        InlineKeyboardButton("❌ Delete", callback_data=f"decline:{uid}"),
                    ],
                    [
                        InlineKeyboardButton("+30d", callback_data=f"grant:{uid}:30"),
                        InlineKeyboardButton("+90d", callback_data=f"grant:{uid}:90"),
                        InlineKeyboardButton("+180d", callback_data=f"grant:{uid}:180"),
                        InlineKeyboardButton("+365d", callback_data=f"grant:{uid}:365"),
                    ],
                ]
            )
            await context.bot.send_message(
                admin,
                f"📨 <b>New contact message</b>\nUser ID: {uid}\n\n{txt}",
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
            )
        await update.message.reply_text("✅ Message sent to admin.")
        active_contact[uid] = False
# =========================================================
# Saved Jobs
# =========================================================
async def saved_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        with get_session() as s:
            u = get_or_create_user_by_tid(s, update.effective_user.id)
            rows = s.execute(
                text(
                    """
                    SELECT sj.job_id, sj.saved_at, je.platform, je.title, je.description,
                           je.affiliate_url, je.original_url, je.budget_amount, je.budget_currency,
                           je.budget_usd, je.created_at
                    FROM saved_job sj
                    LEFT JOIN job_event je ON je.id = sj.job_id
                    WHERE sj.user_id = :uid
                    ORDER BY sj.saved_at DESC
                    LIMIT 10
                    """
                ),
                {"uid": u.id},
            ).fetchall()
        if not rows:
            await update.effective_chat.send_message("💾 No saved jobs yet.")
            return

        for r in rows:
            budget = to_usd(r["budget_amount"] or 0, r["budget_currency"] or "USD")
            msg = (
                f"<b>{r['title']}</b>\n"
                f"<b>Budget:</b> {budget}\n"
                f"<b>Platform:</b> {r['platform']}\n"
                f"<b>Match:</b> (keyword matched)\n"
                f"🕓 Posted: {r['created_at']:%Y-%m-%d %H:%M UTC}\n"
            )
            kb = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("🔗 Original", url=r["original_url"]),
                        InlineKeyboardButton("⭐ Delete", callback_data=f"saved:del:{r['job_id']}"),
                    ]
                ]
            )
            await update.effective_chat.send_message(
                msg, parse_mode=ParseMode.HTML, reply_markup=kb
            )
            await asyncio.sleep(0.3)
    except Exception as e:
        log.exception("saved_cmd error: %s", e)
        await update.effective_chat.send_message("⚠️ Error loading saved jobs.")

# =========================================================
# Admin Panel + Feed Status
# =========================================================
async def feedstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        await update.effective_chat.send_message("⛔ You are not admin.")
        return
    try:
        stats = get_platform_stats(STATS_WINDOW_HOURS) or {}
    except Exception as e:
        await update.effective_chat.send_message(f"Feed status unavailable: {e}")
        return
    if not stats:
        await update.effective_chat.send_message(f"No events in the last {STATS_WINDOW_HOURS}h.")
        return
    msg = "📊 Feed Status (last %dh):\n" % STATS_WINDOW_HOURS
    msg += "\n".join([f"• {k}: {v}" for k, v in stats.items()])
    await update.effective_chat.send_message(msg)

async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        await update.effective_chat.send_message("⛔ Not admin.")
        return
    with get_session() as s:
        rows = s.execute(
            text(
                'SELECT id, telegram_id, trial_end, license_until, is_active, is_blocked '
                'FROM "user" ORDER BY id DESC LIMIT 50'
            )
        ).fetchall()
    lines = ["<b>👥 Users</b>"]
    for r in rows:
        kw = count_keywords(r["id"])
        lines.append(
            f"• <a href=\"tg://user?id={r['telegram_id']}\">{r['telegram_id']}</a> | "
            f"kw:{kw} | trial:{r['trial_end']} | lic:{r['license_until']} | "
            f"A:{'✅' if r['is_active'] else '❌'} | B:{'🚫' if r['is_blocked'] else '✅'}"
        )
    await update.effective_chat.send_message(
        "\n".join(lines), parse_mode=ParseMode.HTML, disable_web_page_preview=True
    )

# =========================================================
# Admin Callback Actions
# =========================================================
async def admin_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data.split(":")
    action = data[0]
    if len(data) < 2:
        return
    target = int(data[1])

    if action == "reply":
        await q.message.reply_text(f"💬 Reply with: /reply {target} <message>")
    elif action == "decline":
        await q.message.edit_text("❌ Message closed.")
    elif action == "grant" and len(data) == 3:
        days = int(data[2])
        until = datetime.now(timezone.utc) + timedelta(days=days)
        with get_session() as s:
            s.execute(
                text('UPDATE "user" SET license_until=:u WHERE telegram_id=:t'),
                {"u": until, "t": target},
            )
            s.commit()
        await context.bot.send_message(
            target,
            f"🎁 Your access has been extended by {days} days — until {until:%Y-%m-%d %H:%M UTC}.",
        )
        await q.edit_message_text(f"✅ Granted +{days}d to {target}")

# =========================================================
# Menu Callback Router
# =========================================================
async def menu_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    await q.answer()

    if data == "act:addkw":
        await addkeyword_cmd(update, context)
    elif data == "act:settings":
        await mysettings_cmd(update, context)
    elif data == "act:help":
        await help_cmd(update, context)
    elif data == "act:saved":
        await saved_cmd(update, context)
    elif data == "act:contact":
        await contact_cmd(update, context)
    elif data == "act:admin":
        await q.edit_message_text("👑 Admin Panel:", reply_markup=admin_menu_kb())
    elif data.startswith("adm:users"):
        await users_cmd(update, context)
    elif data.startswith("adm:feedstatus"):
        await feedstatus_cmd(update, context)
    else:
        await q.edit_message_text("❌ Unknown action.")

# =========================================================
# Application Builder
# =========================================================
def build_application() -> Application:
    ensure_schema()
    ensure_feed_events_schema()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Public commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))
    app.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app.add_handler(CommandHandler("delkeyword", delkeyword_cmd))
    app.add_handler(CommandHandler("clearkeywords", clearkeywords_cmd))
    app.add_handler(CommandHandler("selftest", selftest_cmd))
    app.add_handler(CommandHandler("contact", contact_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))

    # Admin
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CommandHandler("feedstatus", feedstatus_cmd))

    # Callbacks
    app.add_handler(CallbackQueryHandler(menu_action_cb, pattern=r"^act:"))
    app.add_handler(CallbackQueryHandler(admin_action_cb, pattern=r"^(reply|decline|grant):"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_router))

    log.info("✅ Bot application fully built and ready.")
    return app
