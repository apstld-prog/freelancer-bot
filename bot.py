# bot.py — Old layout preserved, new fixes & commands integrated
# EN-only messages (as requested)

import os, re, asyncio, logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Set
from types import SimpleNamespace

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

# Optional JobQueue (graceful fallback)
try:
    from telegram.ext import JobQueue
except Exception:
    JobQueue = None  # type: ignore

from sqlalchemy import text

# --- project imports
from db import ensure_schema, get_session, get_or_create_user_by_tid
from config import ADMIN_IDS, TRIAL_DAYS, STATS_WINDOW_HOURS
from db_events import ensure_feed_events_schema, get_platform_stats, record_event
from db_keywords import (
    list_keywords, add_keywords, count_keywords,
    ensure_keyword_unique, delete_keywords, clear_keywords
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

BOT_TOKEN = (
    os.getenv("TELEGRAM_BOT_TOKEN")
    or os.getenv("BOT_TOKEN")
    or os.getenv("TELEGRAM_TOKEN")
)
if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN env var is required")

# ------------- Helpers (admins, ui, usd) -----------------

FX = {"EUR": 1.08, "GBP": 1.25, "USD": 1.0}  # stable conversion rate (fixed)

def usd_fmt(amount: Optional[float], cur: str) -> str:
    if amount is None:
        return "N/A"
    cur = (cur or "USD").upper()
    usd = amount * (FX.get(cur, 1.0))
    if cur == "USD":
        return f"{amount:.2f} USD"
    return f"{amount:.2f} {cur} (~${usd:.2f} USD)"

def get_db_admin_ids() -> Set[int]:
    try:
        with get_session() as s:
            # Ensure schema fix: add job_id column if missing
            try:
                s.execute(text("ALTER TABLE saved_job ADD COLUMN job_id BIGINT"))
                s.commit()
            except Exception:
                pass

            rows = s.execute(text('SELECT telegram_id FROM "user" WHERE is_admin=TRUE')).fetchall()
            return {int(r["telegram_id"]) for r in rows if r["telegram_id"]}
    except Exception:
        return set()

def all_admin_ids() -> Set[int]:
    seed = set(int(x) for x in (ADMIN_IDS or []))
    return seed | get_db_admin_ids()

def is_admin_user(tid: int) -> bool:
    return tid in all_admin_ids()

def main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    # exact order/labels as in your old bot
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
    # visual “panel” like in your screenshots (Users/Broadcast/Feed Status + Grant License & Block/Unblock)
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("👥 Users", callback_data="adm:users"),
                InlineKeyboardButton("📣 Broadcast", callback_data="adm:broadcast_prompt"),
            ],
            [
                InlineKeyboardButton("📈 Feed Status", callback_data="adm:feedstatus"),
                InlineKeyboardButton("🎁 Grant License", callback_data="adm:grantmenu"),
            ],
            [
                InlineKeyboardButton("🚫 Block", callback_data="adm:block_prompt"),
                InlineKeyboardButton("✅ Unblock", callback_data="adm:unblock_prompt"),
            ],
        ]
    )

HELP_EN = (
    "🧭 <b>Help / How it works</b>\n\n"
    "1️⃣ Add keywords with <code>/addkeyword python, telegram</code> (comma-separated).\n"
    "2️⃣ Set your countries via <code>/setcountry US,UK</code> (or <b>ALL</b>).\n"
    "3️⃣ Save a proposal template with <code>/setproposal &lt;text&gt;</code>\n"
    "   Placeholders: {jobtitle}, {experience}, {stack}, {availability}, {step1}, {step2}, {step3}, {budgettime}, {portfolio}, {name}\n"
    "4️⃣ When a job arrives you can:\n"
    "   ⭐ Keep it  • 🗑 Delete  • 📄 Proposal (affiliate) • 🔗 Original (affiliate)\n\n"
    "• Use <code>/mysettings</code> anytime to review setup.\n"
    "• Try <code>/selftest</code> for 2 sample jobs.\n"
    "• <code>/platforms CC</code> to filter by country (e.g., /platforms GR).\n\n"
    "📚 <b>Platforms monitored:</b>\n"
    "• Global: Freelancer.com (affiliate links), PeoplePerHour, Malt, Workana, Guru, 99designs, Toptal*, Codeable*, YunoJuno*, Worksome*, twago, freelancermap\n"
    "• Greece: JobFind.gr, Skywalker.gr, Kariera.gr\n\n"
    "👑 <b>Admin commands</b>:\n"
    "<code>/users</code> • <code>/grant &lt;telegram_id&gt; &lt;days&gt;</code> • "
    "<code>/block &lt;id&gt;</code> • <code>/unblock &lt;id&gt;</code> • <code>/broadcast &lt;text&gt;</code> • <code>/feedstatus</code>\n"
)

def help_footer(hours: int) -> str:
    return ""  # footer already merged in HELP_EN (kept old long help look)

def welcome_text(expiry: Optional[datetime]) -> str:
    extra = f"\n<b>Free trial ends:</b> {expiry.strftime('%Y-%m-%d %H:%M UTC')}" if expiry else ""
    return (
        "👋 <b>Welcome to Freelancer Alert Bot!</b>\n\n"
        "🎁 You have a <b>10-day free trial</b>.\n"
        "The bot finds freelance jobs from top platforms and sends alerts instantly."
        f"{extra}\n\nUse <code>/help</code> to see how it works."
    )

def settings_text(keywords, countries, proposal_template, trial_start, trial_end, license_until, active, blocked) -> str:
    def tick(v): return "✅" if v else "❌"
    k = ", ".join(keywords) if keywords else "(none)"
    c = countries or "ALL"
    ts = trial_start.isoformat().replace("+00:00", "Z") if trial_start else "—"
    te = trial_end.isoformat().replace("+00:00", "Z") if trial_end else "—"
    lic = "None" if not license_until else license_until.isoformat().replace("+00:00","Z")
    pt = "(saved)" if proposal_template else "(none)"
    return (
        "🛠 <b>Your Settings</b>\n"
        f"• <b>Keywords:</b> {k}\n"
        f"• <b>Countries:</b> {c}\n"
        f"• <b>Proposal template:</b> {pt}\n\n"
        f"● Start date: {ts}\n"
        f"● Trial ends: {te} UTC\n"
        f"🔑 License until: {lic}\n"
        f"✅ Active: {tick(active)}    ⛔ Blocked: {tick(blocked)}\n\n"
        "🛰 <b>Platforms monitored:</b> Global & GR boards."
    )

# ------------- Commands: /start /help /mysettings ---------------

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        # Postgres-safe updates with make_interval
        s.execute(
            'UPDATE "user" SET trial_start=COALESCE(trial_start, NOW() AT TIME ZONE \'UTC\') WHERE id=%(i)s',
            {"i": u.id},
        )
        s.execute(
            'UPDATE "user" SET trial_end=COALESCE(trial_end,(NOW() AT TIME ZONE \'UTC\') + make_interval(days => %(d)s)) WHERE id=%(i)s',
            {"i": u.id, "d": TRIAL_DAYS},
        )
        row = s.execute(
            'SELECT COALESCE(license_until, trial_end) AS expiry FROM "user" WHERE id=%(i)s', {"i": u.id}
        ).fetchone()
        expiry = row["expiry"] if row else None
        s.commit()
    await update.effective_chat.send_message(
        welcome_text(expiry if isinstance(expiry, datetime) else None),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_kb(is_admin=is_admin_user(update.effective_user.id)),
    )
    await update.effective_chat.send_message(
        HELP_EN, parse_mode=ParseMode.HTML, disable_web_page_preview=True
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(
        HELP_EN, parse_mode=ParseMode.HTML, disable_web_page_preview=True
    )

async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        kws = list_keywords(u.id)
        row = s.execute(
            text('SELECT countries, proposal_template, trial_start, trial_end, license_until, is_active, is_blocked FROM "user" WHERE id=:i'),
            {"i": u.id},
        ).fetchone()
    await update.effective_chat.send_message(
        settings_text(
            kws, row["countries"], row["proposal_template"], row["trial_start"], row["trial_end"],
            row["license_until"], bool(row["is_active"]), bool(row["is_blocked"])
        ),
        parse_mode=ParseMode.HTML, disable_web_page_preview=True
    )

# ------------- Keyword management (old UX kept) ---------------

def _parse_keywords(raw: str) -> List[str]:
    parts = [p.strip() for chunk in raw.split(",") for p in chunk.split() if p.strip()]
    seen, out = set(), []
    for p in parts:
        lp = p.lower()
        if lp not in seen:
            seen.add(lp); out.append(p)
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
    n = add_keywords(u.id, kws)
    cur = list_keywords(u.id)
    await update.message.reply_text(
        ("✅ Added %d new keyword(s)." % n if n else "ℹ️ Those keywords already exist.")
        + "\n\nCurrent keywords:\n• " + (", ".join(cur) if cur else "—"),
        parse_mode=ParseMode.HTML,
    )

async def delkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Delete keywords.\nExample: <code>/delkeyword logo, sales</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    kws = _parse_keywords(" ".join(context.args))
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
    removed = delete_keywords(u.id, kws)
    left = list_keywords(u.id)
    await update.message.reply_text(
        f"🗑 Removed {removed}.\n\nCurrent keywords:\n• " + (", ".join(left) if left else "—"),
        parse_mode=ParseMode.HTML,
    )

async def clearkeywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("✅ Yes, clear all", callback_data="kw:clear:yes"),
          InlineKeyboardButton("❌ No", callback_data="kw:clear:no")]]
    )
    await update.message.reply_text("Clear ALL your keywords?", reply_markup=kb)

# ------------- Save/Clear keywords callbacks ----------------

async def kw_clear_confirm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if (q.data or "") != "kw:clear:yes":
        await q.edit_message_text("Cancelled.")
        return
    with get_session() as s:
        u = get_or_create_user_by_tid(s, q.from_user.id)
    n = clear_keywords(u.id)
    await q.edit_message_text(f"🗑 Cleared {n} keyword(s).")

# ------------- Contact (two-way chat like old bot) ------------

def _pairstore(app: Application):
    return app.bot_data.setdefault("pairs", {"u2a": {}, "a2u": {}})

def pair_admin_user(app: Application, admin_id: int, user_id: int) -> None:
    p = _pairstore(app)
    p["u2a"][user_id] = admin_id
    p["a2u"][admin_id] = user_id

def get_paired_admin(app: Application, user_id: int) -> Optional[int]:
    return _pairstore(app)["u2a"].get(user_id)

def get_paired_user(app: Application, admin_id: int) -> Optional[int]:
    return _pairstore(app)["a2u"].get(admin_id)

def unpair(app: Application, admin_id: Optional[int] = None, user_id: Optional[int] = None):
    p = _pairstore(app)
    if admin_id is not None:
        uid = p["a2u"].pop(admin_id, None)
        if uid is not None:
            p["u2a"].pop(uid, None)
    if user_id is not None:
        aid = p["u2a"].pop(user_id, None)
        if aid is not None:
            p["a2u"].pop(aid, None)

async def contact_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(
        "✉️ Send a message to admin below. Type <code>/cancel</code> to stop chatting.",
        parse_mode=ParseMode.HTML,
    )
    # fan out first message to all admins so one can pick up with Reply button
    txt = "📩 <b>New message from user</b>\nID: <code>%d</code>\n\n(Waiting for your reply…)" % update.effective_user.id
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("💬 Reply", callback_data=f"adm:reply:{update.effective_user.id}"),
             InlineKeyboardButton("❌ Decline", callback_data=f"adm:decline:{update.effective_user.id}")],
            [InlineKeyboardButton("+30d", callback_data=f"adm:grant:{update.effective_user.id}:30"),
             InlineKeyboardButton("+90d", callback_data=f"adm:grant:{update.effective_user.id}:90")],
            [InlineKeyboardButton("+180d", callback_data=f"adm:grant:{update.effective_user.id}:180"),
             InlineKeyboardButton("+365d", callback_data=f"adm:grant:{update.effective_user.id}:365")],
        ]
    )
    for aid in all_admin_ids():
        try:
            await context.bot.send_message(aid, txt, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            pass

async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    unpair(context.application, user_id=update.effective_user.id, admin_id=None)
    await update.message.reply_text("Chat cancelled.")

async def incoming_message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # route plain text messages inside the chat tunnel
    if not update.message or not update.message.text or update.message.text.startswith("/"):
        return
    sender = update.effective_user.id
    app = context.application
    if is_admin_user(sender):
        target = get_paired_user(app, sender)
        if target:
            try:
                await context.bot.send_message(target, update.message.text)
            except Exception:
                pass
            return
    target_admin = get_paired_admin(app, sender)
    if target_admin:
        try:
            await context.bot.send_message(
                target_admin,
                f"✉️ From {sender}:\n\n{update.message.text}",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("💬 Reply", callback_data=f"adm:reply:{sender}"),
                         InlineKeyboardButton("❌ Decline", callback_data=f"adm:decline:{sender}")],
                        [InlineKeyboardButton("+30d", callback_data=f"adm:grant:{sender}:30"),
                         InlineKeyboardButton("+90d", callback_data=f"adm:grant:{sender}:90")],
                        [InlineKeyboardButton("+180d", callback_data=f"adm:grant:{sender}:180"),
                         InlineKeyboardButton("+365d", callback_data=f"adm:grant:{sender}:365")],
                    ]
                ),
            )
        except Exception:
            pass
        return
    # first time message without explicit /contact
    for aid in all_admin_ids():
        try:
            await context.bot.send_message(
                aid,
                f"✉️ <b>New message from user</b>\nID: <code>{sender}</code>\n\n{update.message.text}",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("💬 Reply", callback_data=f"adm:reply:{sender}"),
                         InlineKeyboardButton("❌ Decline", callback_data=f"adm:decline:{sender}")],
                        [InlineKeyboardButton("+30d", callback_data=f"adm:grant:{sender}:30"),
                         InlineKeyboardButton("+90d", callback_data=f"adm:grant:{sender}:90")],
                        [InlineKeyboardButton("+180d", callback_data=f"adm:grant:{sender}:180"),
                         InlineKeyboardButton("+365d", callback_data=f"adm:grant:{sender}:365")],
                    ]
                ),
            )
        except Exception:
            pass
    await update.message.reply_text("Thanks! Your message was forwarded to the admin 👌")

# ------------- Admin commands & callbacks -------------------

async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        await update.effective_chat.send_message("⛔ Not admin."); return
    with get_session() as s:
        rows = s.execute(
            text('SELECT id, telegram_id, trial_end, license_until, is_active, is_blocked FROM "user" ORDER BY id DESC LIMIT 100')
        ).fetchall()
    out = ["<b>👥 Users</b>"]
    for r in rows:
        kwc = count_keywords(r["id"])
        out.append(
            f"• <a href=\"tg://user?id={r['telegram_id']}\">{r['telegram_id']}</a> — "
            f"kw:{kwc} | trial:{r['trial_end']} | lic:{r['license_until']} | "
            f"A:{'✅' if r['is_active'] else '❌'} B:{'✅' if r['is_blocked'] else '❌'}"
        )
    await update.effective_chat.send_message("\n".join(out), parse_mode=ParseMode.HTML)

async def feedstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        return
    try:
        stats = get_platform_stats(STATS_WINDOW_HOURS) or {}
    except Exception as e:
        await update.effective_chat.send_message(f"Feed status unavailable: {e}")
        return
    if not stats:
        await update.effective_chat.send_message(f"No events in the last {STATS_WINDOW_HOURS}h.")
        return
    msg = "📊 <b>Feed status</b> (last %dh):\n" % STATS_WINDOW_HOURS
    msg += "\n".join([f"• {k}: {v}" for k, v in stats.items()])
    await update.effective_chat.send_message(msg, parse_mode=ParseMode.HTML)

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        return
    if not context.args:
        await update.effective_chat.send_message("Usage: /broadcast <text>"); return
    txt = " ".join(context.args)
    with get_session() as s:
        rows = s.execute(text('SELECT telegram_id FROM "user" WHERE is_active=TRUE AND is_blocked=FALSE')).fetchall()
    sent = 0
    for r in rows:
        try:
            await context.bot.send_message(r["telegram_id"], txt, parse_mode=ParseMode.HTML)
            sent += 1
        except Exception:
            pass
    await update.effective_chat.send_message(f"📣 Broadcast sent to {sent} users.")

async def grant_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id): return
    if len(context.args) < 2:
        await update.effective_chat.send_message("Usage: /grant <telegram_id> <days>"); return
    tid = int(context.args[0]); days = int(context.args[1])
    until = datetime.now(timezone.utc) + timedelta(days=days)
    with get_session() as s:
        s.execute(text('UPDATE "user" SET license_until=:u WHERE telegram_id=:t'), {"u": until, "t": tid})
        s.commit()
    try:
        await context.bot.send_message(tid, f"🔑 Your access is extended until {until.strftime('%Y-%m-%d %H:%M UTC')}.")
    except Exception:
        pass
    await update.effective_chat.send_message("✅ Granted.")

async def block_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id): return
    parts = (update.message.text or "").split()
    if len(parts) < 2:
        await update.effective_chat.send_message("Usage: /block <telegram_id>"); return
    tid = int(parts[1])
    with get_session() as s:
        s.execute(text('UPDATE "user" SET is_blocked=TRUE WHERE telegram_id=:t'), {"t": tid}); s.commit()
    await update.effective_chat.send_message("⛔ Blocked.")

async def unblock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id): return
    parts = (update.message.text or "").split()
    if len(parts) < 2:
        await update.effective_chat.send_message("Usage: /unblock <telegram_id>"); return
    tid = int(parts[1])
    with get_session() as s:
        s.execute(text('UPDATE "user" SET is_blocked=FALSE WHERE telegram_id=:t'), {"t": tid}); s.commit()
    await update.effective_chat.send_message("✅ Unblocked.")

# inline admin actions: reply/decline/grant+days
async def inline_admin_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = (q.data or "")
    if data.startswith("adm:reply:"):
        target = int(data.split(":")[2])
        pair_admin_user(context.application, q.from_user.id, target)
        await q.message.reply_text(
            f"💬 Replying to <code>{target}</code>. Send messages directly. /cancel to stop.",
            parse_mode=ParseMode.HTML,
        )
        return
    if data.startswith("adm:decline:"):
        target = int(data.split(":")[2])
        unpair(context.application, user_id=target)
        await q.message.reply_text("❌ Declined.")
        return
    if data.startswith("adm:grant:"):
        parts = data.split(":")
        target = int(parts[2]); days = int(parts[3])
        until = datetime.now(timezone.utc) + timedelta(days=days)
        with get_session() as s:
            s.execute(text('UPDATE "user" SET license_until=:u WHERE telegram_id=:t'),
                      {"u": until, "t": target}); s.commit()
        try:
            await context.bot.send_message(target, f"🎁 Your access is extended until {until.strftime('%Y-%m-%d %H:%M UTC')}.")
        except Exception:
            pass
        await q.message.reply_text(f"✅ Granted +{days}d.")
        return

# ------------- Saved Jobs List -----------------

async def saved_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show saved jobs with working buttons (only real linked jobs)."""
    user_id = update.effective_user.id
    try:
        with get_session() as s:
            rows = s.execute(text("""
                SELECT sj.saved_at, je.platform, je.title, je.description,
                       je.affiliate_url, je.original_url, je.budget_amount,
                       je.budget_currency, je.budget_usd, je.created_at
                FROM saved_job sj
                JOIN job_event je ON je.id = sj.job_id
                WHERE sj.user_id = :uid
                AND je.id IS NOT NULL
                ORDER BY sj.saved_at DESC
                LIMIT 10
            """), {"uid": user_id}).fetchall()

        if not rows:
            await update.effective_chat.send_message("💾 No saved jobs yet.")
            return

        for r in rows:
            title = r.title or "(no title)"
            desc = (r.description or "").strip()
            platform = r.platform or "Unknown"
            budget = f"{r.budget_amount or 'N/A'} {r.budget_currency or ''}".strip()
            usd = f" (~${r.budget_usd:.2f} USD)" if r.budget_usd else ""
            posted = (
                r.created_at.strftime("%Y-%m-%d %H:%M UTC")
                if r.created_at else "N/A"
            )

            proposal_url = r.affiliate_url or r.original_url or "https://freelancer.com"
            original_url = r.original_url or "https://freelancer.com"

            msg = (
                f"<b>{title}</b>\n"
                f"💰 <b>Budget:</b> {budget}{usd}\n"
                f"🌐 <b>Source:</b> {platform}\n"
                f"📝 {desc[:400]}\n"
                f"🕓 <b>Posted:</b> {posted}"
            )

            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📄 Proposal", url=proposal_url),
                    InlineKeyboardButton("🔗 Original", url=original_url)
                ],
                [
                    InlineKeyboardButton("🗑 Delete", callback_data="job:delete")
                ]
            ])

            await update.effective_chat.send_message(
                msg, parse_mode=ParseMode.HTML, reply_markup=kb
            )

    except Exception as e:
        log.exception("saved_cmd error: %s", e)
        await update.effective_chat.send_message(
            f"⚠️ Saved list unavailable.\nError: {e}"
        )

# ------------- Job card actions (Save/Delete) -----------------

def _extract_card_title(text_html: str) -> str:
    m = re.search(r"<b>([^<]+)</b>", text_html or "", flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return (text_html or "").splitlines()[0][:200] or "Saved job"

async def job_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles Save/Delete from job cards"""
    q = update.callback_query
    await q.answer()
    msg = q.message
    data = q.data

    if data == "job:save":
        try:
            with get_session() as s:
                u = get_or_create_user_by_tid(s, update.effective_user.id)

                # Extract safely
                text_html = (
                    getattr(msg, "text_html", None)
                    or getattr(msg, "caption_html", None)
                    or getattr(msg, "text", None)
                    or getattr(msg, "caption", None)
                    or ""
                )

                title = _extract_card_title(text_html)
                dedup = f"manual::{abs(hash(title)) % 10000000}"

                original_url = ""
                try:
                    if msg and msg.reply_markup and msg.reply_markup.inline_keyboard:
                        first_row = msg.reply_markup.inline_keyboard[0]
                        if len(first_row) > 1 and getattr(first_row[1], "url", None):
                            original_url = first_row[1].url or ""
                        elif len(first_row) >= 1 and getattr(first_row[0], "url", None):
                            original_url = first_row[0].url or ""
                except Exception:
                    pass

                # Insert job
                je = s.execute(text("""
                    INSERT INTO job_event (
                        platform, title, description, affiliate_url, original_url,
                        budget_amount, budget_currency, budget_usd, created_at, dedup_key
                    )
                    VALUES (:p, :t, :d, :a, :o, :ba, :bc, :bu, NOW() AT TIME ZONE 'UTC', :dk)
                    
                    RETURNING id
                """), {
                    "p": "manual",
                    "t": title,
                    "d": text_html,
                    "a": original_url,
                    "o": original_url,
                    "ba": None,
                    "bc": "USD",
                    "bu": None,
                    "dk": dedup
                }).fetchone()

                s.execute(
                    text("INSERT INTO saved_job (user_id, job_id) VALUES (:u, :j)"),
                    {"u": u.id, "j": je["id"]}
                )
                s.commit()

            await msg.delete()
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="✅ Job saved successfully."
            )

        except Exception as e:
            log.exception("job:save error: %s", e)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"⚠️ Save failed: {e}"
            )
        return

async def saved_delete_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not (q.data or "").startswith("saved:del:"):
        return
    try:
        job_id = int(q.data.split(":")[2])
    except Exception:
        return
    try:
        with get_session() as s:
            u = get_or_create_user_by_tid(s, q.from_user.id)
            s.execute(text("DELETE FROM saved_job WHERE user_id=:u AND job_id=:j"), {"u": u.id, "j": job_id})
            s.commit()
        try:
            if q.message: await q.message.delete()
        except Exception:
            pass
    except Exception as e:
        log.exception("saved delete error: %s", e)

async def selftest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show 2 sample jobs (same visual layout as your old bot)"""
    try:
        # --- Example 1
        txt1 = (
            "<b>Design a Modern Company Logo</b>\n"
            f"💰 <b>Budget:</b> 50.00 EUR (~${50.00*FX['EUR']:.2f} USD)\n"
            "🌐 <b>Source:</b> Freelancer\n"
            "🔍 <b>Match:</b> logo\n"
            "📝 Please redesign my existing company logo.\n"
            f"🕓 <b>Posted:</b> {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}"
        )
        kb1 = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📄 Proposal", url="https://www.freelancer.com/projects/sample"),
                InlineKeyboardButton("🔗 Original", url="https://www.freelancer.com/projects/sample")
            ],
            [
                InlineKeyboardButton("⭐ Save", callback_data="job:save"),
                InlineKeyboardButton("🗑 Delete", callback_data="job:delete")
            ],
        ])
        await update.effective_chat.send_message(txt1, parse_mode=ParseMode.HTML, reply_markup=kb1)
        record_event("freelancer")

        # --- Example 2
        txt2 = (
            "<b>Landing Page Development</b>\n"
            f"💰 <b>Budget:</b> 120.00 USD (~${120.00*FX['USD']:.2f} USD)\n"
            "🌐 <b>Source:</b> PeoplePerHour\n"
            "🔍 <b>Match:</b> wordpress\n"
            "📝 Create responsive landing page for a new service.\n"
            f"🕓 <b>Posted:</b> {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}"
        )
        kb2 = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📄 Proposal", url="https://www.peopleperhour.com/freelance-jobs/sample"),
                InlineKeyboardButton("🔗 Original", url="https://www.peopleperhour.com/freelance-jobs/sample")
            ],
            [
                InlineKeyboardButton("⭐ Save", callback_data="job:save"),
                InlineKeyboardButton("🗑 Delete", callback_data="job:delete")
            ],
        ])
        await update.effective_chat.send_message(txt2, parse_mode=ParseMode.HTML, reply_markup=kb2)
        record_event("peopleperhour")

        await update.effective_chat.send_message("✅ Self-test completed — 2 sample jobs posted.")
    except Exception as e:
        log.exception("selftest error: %s", e)
        await update.effective_chat.send_message("⚠️ Self-test failed.")
# ------------- Menu actions router (keeps old menu behaviour) ---------

async def menu_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = (q.data or "")
    await q.answer()

    if data == "act:addkw":
        await addkeyword_cmd(update, context); return
    if data == "act:settings":
        await mysettings_cmd(update, context); return
    if data == "act:help":
        await help_cmd(update, context); return
    if data == "act:saved":
        await saved_cmd(update, context); return
    if data == "act:contact":
        await contact_cmd(update, context); return
    if data == "act:admin":
        if not is_admin_user(q.from_user.id):
            await q.answer("Not allowed", show_alert=True); return
        await q.message.reply_text("👑 Admin Panel", reply_markup=admin_menu_kb()); return

    # admin panel buttons
    if data == "adm:users":
        await users_cmd(update, context); return
    if data == "adm:feedstatus":
        await feedstatus_cmd(update, context); return
    if data == "adm:broadcast_prompt":
        await q.message.reply_text("Send: /broadcast <text>"); return
    if data == "adm:block_prompt":
        await q.message.reply_text("Send: /block <telegram_id>"); return
    if data == "adm:unblock_prompt":
        await q.message.reply_text("Send: /unblock <telegram_id>"); return
    if data == "adm:grantmenu":
        await q.message.reply_text(
            "Tap a grant button on any user message (Reply panel appears when user chats)."
        ); return

    await q.edit_message_text("❌ Unknown action.")

# ------------- Expiry reminders (hourly) ---------------------

async def notify_expiring_job(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(timezone.utc); soon = now + timedelta(hours=24)
    with get_session() as s:
        rows = s.execute(text(
            'SELECT telegram_id, COALESCE(license_until, trial_end) AS expiry '
            'FROM "user" WHERE is_active=TRUE AND is_blocked=FALSE'
        )).fetchall()
    for r in rows:
        exp = r["expiry"]
        if not exp: continue
        if getattr(exp, "tzinfo", None) is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if now < exp <= soon:
            try:
                left = int((exp - now).total_seconds() // 3600)
                await context.bot.send_message(
                    r["telegram_id"],
                    f"⏰ Reminder: your access expires in about {left} hours (on {exp.strftime('%Y-%m-%d %H:%M UTC')})."
                )
            except Exception:
                pass

# ------------- Application builder ---------------------------

def build_application() -> Application:
    ensure_schema()
    ensure_feed_events_schema()
    ensure_keyword_unique()

    # --- Ensure job_event schema fixes ---
    try:
        with get_session() as s:
            s.execute(text("""
                ALTER TABLE job_event
                ADD COLUMN IF NOT EXISTS budget_usd NUMERIC;
            """))
            s.commit()
            log.info("✅ job_event schema verified (budget_usd OK)")
    except Exception as e:
        log.warning(f"⚠️ Could not verify job_event schema: {e}")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # public commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))
    app.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app.add_handler(CommandHandler("delkeyword", delkeyword_cmd))
    app.add_handler(CommandHandler("clearkeywords", clearkeywords_cmd))
    app.add_handler(CommandHandler("selftest", selftest_cmd))
    app.add_handler(CommandHandler("contact", contact_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))

    # admin commands
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("grant", grant_cmd))
    app.add_handler(CommandHandler("block", block_cmd))
    app.add_handler(CommandHandler("unblock", unblock_cmd))
    app.add_handler(CommandHandler("feedstatus", feedstatus_cmd))

    # callbacks
    app.add_handler(CallbackQueryHandler(menu_action_cb, pattern=r"^(act|adm):"))
    app.add_handler(CallbackQueryHandler(kw_clear_confirm_cb, pattern=r"^kw:clear:(yes|no)$"))
    app.add_handler(CallbackQueryHandler(inline_admin_action_cb, pattern=r"^adm:(reply|decline|grant):"))
    app.add_handler(CallbackQueryHandler(saved_delete_cb, pattern=r"^saved:del:\d+$"))
    app.add_handler(CallbackQueryHandler(job_action_cb, pattern=r"^job:(save|delete)$"))

    # free text router (for contact chat)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, incoming_message_router))

    # scheduler (hourly)
    try:
        if JobQueue is not None:
            jq = app.job_queue or JobQueue()
            if app.job_queue is None:
                jq.set_application(app)
            jq.run_repeating(notify_expiring_job, interval=3600, first=60)
            log.info("Scheduler: JobQueue")
        else:
            raise RuntimeError("no jobqueue")
    except Exception:
        try:
            app.bot_data["expiry_task"] = asyncio.get_event_loop().create_task(
                notify_expiring_job(SimpleNamespace(bot=app.bot))  # one-off
            )
        except Exception:
            pass

    return app
