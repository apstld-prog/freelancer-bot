# bot.py — EN-only UX, continuous chat, robust keywords (column=keyword), admin fixes, safe scheduler
import os
import logging
import asyncio
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
from typing import List, Set, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)

# Optional JobQueue (works if PTB extra installed); else we use fallback loop
try:
    from telegram.ext import JobQueue
except Exception:
    JobQueue = None  # type: ignore

# ---- project-local modules
from db import (
    ensure_schema, get_session, get_or_create_user_by_tid,
    User,
)
from config import ADMIN_IDS, TRIAL_DAYS, STATS_WINDOW_HOURS
from db_events import ensure_feed_events_schema, get_platform_stats

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

log = logging.getLogger("bot")
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN env var is required")
ADMIN_ELEVATE_SECRET = os.getenv("ADMIN_ELEVATE_SECRET", "")

# ============= Admin helpers =============
def get_db_admin_ids() -> Set[int]:
    try:
        with get_session() as s:
            rows = s.execute(text("SELECT telegram_id FROM \"user\" WHERE is_admin = TRUE")).fetchall()
        return {int(r[0]) for r in rows if r[0]}
    except Exception:
        return set()

def all_admin_ids() -> Set[int]:
    return set(int(x) for x in (ADMIN_IDS or [])) | get_db_admin_ids()

def is_admin_user(uid: int) -> bool:
    return uid in all_admin_ids()

# ============= UI text/keyboard =============
def main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
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
    "<b>1)</b> Add keywords with <code>/addkeyword</code> (comma-separated) or via the “Add Keywords” button.\n"
    "<b>2)</b> Set countries with <code>/setcountry</code> (e.g. <i>US,UK</i> or <i>ALL</i>).\n"
    "<b>3)</b> Save a proposal template with <code>/setproposal &lt;text&gt;</code> (placeholders supported).\n"
    "<b>4)</b> When a job arrives you can keep/delete it or open <b>Proposal</b>/<b>Original</b> link.\n\n"
    "Use <code>/mysettings</code> anytime. Try <code>/selftest</code> for a sample card.\n"
)

def help_footer(hours: int) -> str:
    return (
        "\n<b>🛰 Platforms monitored:</b>\n"
        "• Global: <a href=\"https://www.freelancer.com\">Freelancer.com</a> (affiliate), PeoplePerHour, Malt, Workana, Guru, 99designs, "
        "Toptal*, Codeable*, YunoJuno*, Worksome*, twago, freelancermap\n"
        "• Greece: <a href=\"https://www.jobfind.gr\">JobFind.gr</a>, "
        "<a href=\"https://www.skywalker.gr\">Skywalker.gr</a>, <a href=\"https://www.kariera.gr\">Kariera.gr</a>\n\n"
        "<b>👑 Admin:</b> <code>/users</code> <code>/grant &lt;id&gt; &lt;days&gt;</code> "
        "<code>/block &lt;id&gt;</code> <code>/unblock &lt;id&gt;</code> <code>/broadcast &lt;text&gt;</code> "
        "<code>/feedstatus</code> (alias <code>/feetstatus</code>)\n"
        "<i>Link previews disabled for clean help.</i>\n"
    )

def welcome_text(expiry: Optional[datetime]) -> str:
    extra = f"\n<b>Free trial ends:</b> {expiry.strftime('%Y-%m-%d %H:%M UTC')}" if expiry else ""
    return (
        "<b>👋 Welcome to Freelancer Alert Bot!</b>\n\n"
        "🎁 You have a <b>10-day free trial</b>.\n"
        "The bot finds matching freelance jobs from top platforms and sends instant alerts."
        f"{extra}\n\nUse <code>/help</code> for instructions.\n"
    )

def settings_text(keywords: List[str], countries: str | None, proposal_template: str | None,
                  trial_start, trial_end, license_until, active: bool, blocked: bool) -> str:
    def b(v: bool) -> str: return "✅" if v else "❌"
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
        "<b>🛰 Platforms monitored:</b> Global & GR boards.\n"
        "<i>For extension, contact the admin.</i>"
    )

# ============= Keywords DAO (direct SQL, column name = keyword) =============
def parse_keywords(raw: str) -> List[str]:
    parts = [p.strip() for chunk in raw.split(",") for p in chunk.split() if p.strip()]
    out, seen = [], set()
    for p in parts:
        low = p.lower()
        if low not in seen:
            seen.add(low)
            out.append(p)
    return out

def list_keywords(user_id: int) -> List[str]:
    with get_session() as s:
        rows = s.execute(text("SELECT keyword FROM keyword WHERE user_id=:uid ORDER BY created_at NULLS LAST, id"),
                         {"uid": user_id}).fetchall()
        return [r[0] for r in rows]

def count_keywords(user_id: int) -> int:
    with get_session() as s:
        return int(s.execute(text("SELECT COUNT(*) FROM keyword WHERE user_id=:uid"), {"uid": user_id}).scalar() or 0)

def add_keywords(user_id: int, kws: List[str]) -> int:
    if not kws:
        return 0
    inserted = 0
    with get_session() as s:
        for kw in kws:
            try:
                # Στήλη ονόματι `keyword` (ΟΧΙ value). Αν υπάρχει unique constraint, το ON CONFLICT θα ήταν ιδανικό.
                s.execute(text("INSERT INTO keyword (user_id, keyword) VALUES (:uid, :kw)"),
                          {"uid": user_id, "kw": kw})
                inserted += 1
            except IntegrityError:
                # π.χ. duplicate (αν έχεις μοναδικότητα) — αγνόησέ το
                s.rollback()
            except Exception:
                s.rollback()
                raise
        s.commit()
    return inserted

# ============= Contact pairing helpers =============
def admin_contact_kb(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Reply", callback_data=f"adm:reply:{user_id}"),
         InlineKeyboardButton("❌ Decline", callback_data=f"adm:decline:{user_id}")],
        [InlineKeyboardButton("+30d", callback_data=f"adm:grant:{user_id}:30"),
         InlineKeyboardButton("+90d", callback_data=f"adm:grant:{user_id}:90"),
         InlineKeyboardButton("+180d", callback_data=f"adm:grant:{user_id}:180"),
         InlineKeyboardButton("+365d", callback_data=f"adm:grant:{user_id}:365")],
    ])

def pair_admin_user(app: Application, admin_id: int, user_id: int) -> None:
    pairs = app.bot_data.setdefault("contact_pairs", {"user_to_admin": {}, "admin_to_user": {}})
    pairs["user_to_admin"][user_id] = admin_id
    pairs["admin_to_user"][admin_id] = user_id

def unpair_admin_user(app: Application, admin_id: Optional[int] = None, user_id: Optional[int] = None) -> None:
    pairs = app.bot_data.setdefault("contact_pairs", {"user_to_admin": {}, "admin_to_user": {}})
    if admin_id is not None:
        uid = pairs["admin_to_user"].pop(admin_id, None)
        if uid is not None:
            pairs["user_to_admin"].pop(uid, None)
    if user_id is not None:
        aid = pairs["user_to_admin"].pop(user_id, None)
        if aid is not None:
            pairs["admin_to_user"].pop(aid, None)

def get_paired_admin(app: Application, user_id: int) -> Optional[int]:
    return app.bot_data.setdefault("contact_pairs", {"user_to_admin": {}, "admin_to_user": {}})["user_to_admin"].get(user_id)

def get_paired_user(app: Application, admin_id: int) -> Optional[int]:
    return app.bot_data.setdefault("contact_pairs", {"user_to_admin": {}, "admin_to_user": {}})["admin_to_user"].get(admin_id)

# ============= Commands =============
async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Your Telegram ID: <code>{update.effective_user.id}</code>", parse_mode=ParseMode.HTML)

async def sudo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: <code>/sudo &lt;secret&gt;</code>", parse_mode=ParseMode.HTML); return
    if not ADMIN_ELEVATE_SECRET or " ".join(context.args).strip() != ADMIN_ELEVATE_SECRET:
        await update.message.reply_text("Invalid or missing secret."); return
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        s.execute(text("UPDATE \"user\" SET is_admin=TRUE WHERE id=:id"), {"id": u.id})
        s.commit()
    await update.message.reply_text("✅ You are now an admin. Use /users to verify.")

async def endchat_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_admin_user(uid):
        target = get_paired_user(context.application, uid)
        unpair_admin_user(context.application, admin_id=uid)
        await update.message.reply_text("Chat ended.")
        if target:
            try: await context.bot.send_message(chat_id=target, text="The admin ended the chat.")
            except Exception: pass
    else:
        target_admin = get_paired_admin(context.application, uid)
        unpair_admin_user(context.application, user_id=uid)
        await update.message.reply_text("Chat ended.")
        if target_admin:
            try: await context.bot.send_message(chat_id=target_admin, text=f"User {uid} ended the chat.")
            except Exception: pass

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        if not getattr(u, "trial_start", None):
            s.execute(text("UPDATE \"user\" SET trial_start=NOW() AT TIME ZONE 'UTC' WHERE id=:id"), {"id": u.id})
        if not getattr(u, "trial_end", None):
            s.execute(text("UPDATE \"user\" SET trial_end=(NOW() AT TIME ZONE 'UTC') + INTERVAL ':days days' WHERE id=:id")
                      .bindparams(days=TRIAL_DAYS), {"id": u.id})
        row = s.execute(text(
            "SELECT COALESCE(license_until, trial_end) FROM \"user\" WHERE id=:id"
        ), {"id": u.id}).scalar()
        s.commit()
    expiry = row if isinstance(row, datetime) else None

    if context.application and context.application.bot_data.get("start_fallback_on_first_update"):
        await _ensure_fallback_running(context.application)
        context.application.bot_data.pop("start_fallback_on_first_update", None)

    await update.effective_chat.send_message(
        welcome_text(expiry), parse_mode=ParseMode.HTML,
        reply_markup=main_menu_kb(is_admin=is_admin_user(update.effective_user.id)),
    )
    await update.effective_chat.send_message(features_text(), parse_mode=ParseMode.HTML)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(HELP_EN + help_footer(STATS_WINDOW_HOURS),
                                             parse_mode=ParseMode.HTML, disable_web_page_preview=True)

async def addkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Add keywords separated by commas. Example:\n<code>/addkeyword logo, lighting</code>",
                                        parse_mode=ParseMode.HTML); return
    await _add_keywords_flow(update, context, " ".join(context.args))

async def keywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        curr = list_keywords(u.id)
    await update.message.reply_text(
        "<b>Keywords</b>\n• " + (", ".join(curr) if curr else "—") +
        "\n\nAdd: <code>/addkeyword logo, lighting</code>\nExit inline add: <code>/done</code>",
        parse_mode=ParseMode.HTML)

async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        kws = list_keywords(u.id)
        row = s.execute(text(
            "SELECT countries, proposal_template, trial_start, trial_end, license_until, is_active, is_blocked "
            "FROM \"user\" WHERE id=:id"
        ), {"id": u.id}).fetchone()
    countries, pt, ts, te, lic, active, blocked = row
    await update.message.reply_text(
        settings_text(kws, countries or "ALL", pt, ts, te, lic, bool(active), bool(blocked)),
        parse_mode=ParseMode.HTML, disable_web_page_preview=True)

async def selftest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    job_text = (
        "<b>Email Signature from Existing Logo</b>\n"
        "<b>Budget:</b> 10.0–30.0 USD\n"
        "<b>Source:</b> Freelancer\n"
        "<b>Match:</b> logo\n"
        "✏️ Please create an editable version of the email signature based on the provided logo.\n"
    )
    url = "https://www.freelancer.com/get/apstld?f=give&dl=https://www.freelancer.com/projects/sample"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Proposal", url=url),
         InlineKeyboardButton("🔗 Original", url=url)],
        [InlineKeyboardButton("⭐ Save", callback_data="job:save"),
         InlineKeyboardButton("🗑️ Delete", callback_data="job:delete")],
    ])
    await update.effective_chat.send_message(job_text, parse_mode=ParseMode.HTML, reply_markup=kb)

# ============= Admin commands =============
async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        await update.message.reply_text("You are not an admin. If you should be, use /sudo &lt;secret&gt;.", parse_mode=ParseMode.HTML)
        return
    with get_session() as s:
        rows = s.execute(text(
            "SELECT id, telegram_id, trial_end, license_until, is_active, is_blocked FROM \"user\" ORDER BY id DESC LIMIT 200"
        )).fetchall()
    lines = ["<b>Users</b>"]
    for uid, tid, trial_end, lic, act, blk in rows:
        kwc = count_keywords(uid)
        active, blocked = ("✅" if act else "❌"), ("✅" if blk else "❌")
        lines.append(
            f"• <a href=\"tg://user?id={tid}\">{tid}</a> — kw:{kwc} | trial:{trial_end} | lic:{lic} | A:{active} B:{blocked}"
        )
    await update.effective_chat.send_message("\n".join(lines), parse_mode=ParseMode.HTML)

async def grant_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id): return
    if len(context.args) < 2:
        await update.effective_chat.send_message("Usage: /grant <id> <days>"); return
    tg_id = int(context.args[0]); days = int(context.args[1])
    until = datetime.now(timezone.utc) + timedelta(days=days)
    with get_session() as s:
        s.execute(text("UPDATE \"user\" SET license_until=:dt WHERE telegram_id=:tid"),
                  {"dt": until, "tid": tg_id})
        s.commit()
    await update.effective_chat.send_message(f"✅ Granted until {until.isoformat()} for {tg_id}.")
    try: await context.bot.send_message(chat_id=tg_id, text=f"🔑 Your access is extended until {until.strftime('%Y-%m-%d %H:%M UTC')}.")
    except Exception: pass

async def block_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id): return
    if not context.args: await update.effective_chat.send_message("Usage: /block <id>"); return
    tg_id = int(context.args[0])
    with get_session() as s:
        s.execute(text("UPDATE \"user\" SET is_blocked=TRUE WHERE telegram_id=:tid"), {"tid": tg_id})
        s.commit()
    await update.effective_chat.send_message(f"⛔ Blocked {tg_id}.")

async def unblock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id): return
    if not context.args: await update.effective_chat.send_message("Usage: /unblock <id>"); return
    tg_id = int(context.args[0])
    with get_session() as s:
        s.execute(text("UPDATE \"user\" SET is_blocked=FALSE WHERE telegram_id=:tid"), {"tid": tg_id})
        s.commit()
    await update.effective_chat.send_message(f"✅ Unblocked {tg_id}.")

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id): return
    if not context.args: await update.effective_chat.send_message("Usage: /broadcast <text>"); return
    text_msg = " ".join(context.args)
    with get_session() as s:
        ids = [r[0] for r in s.execute(text(
            "SELECT telegram_id FROM \"user\" WHERE is_active=TRUE AND is_blocked=FALSE"
        )).fetchall()]
    sent = 0
    for tid in ids:
        try:
            await context.bot.send_message(chat_id=tid, text=text_msg, parse_mode=ParseMode.HTML)
            sent += 1
        except Exception:
            pass
    await update.effective_chat.send_message(f"📣 Broadcast sent to {sent} users.")

async def feedstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id): return
    try:
        stats = get_platform_stats(STATS_WINDOW_HOURS) or {}
    except Exception as e:
        await update.effective_chat.send_message(f"Feed status unavailable: {e}"); return
    if not stats:
        await update.effective_chat.send_message(f"No events in the last {STATS_WINDOW_HOURS} hours."); return
    lines = [f"📊 Feed status (last {STATS_WINDOW_HOURS}h):"] + [f"• {src}: {cnt}" for src, cnt in stats.items()]
    await update.effective_chat.send_message("\n".join(lines))

async def feetstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await feedstatus_cmd(update, context)

# ============= Callbacks =============
async def menu_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = (q.data or "").strip()

    if data == "act:addkw":
        context.user_data["awaiting_keywords"] = True
        await q.message.reply_text(
            "Type keywords (comma-separated). Example:\n<code>logo, lighting</code>\n"
            "Finish with <code>/done</code>.",
            parse_mode=ParseMode.HTML,
        ); await q.answer(); return

    if data == "act:settings":
        with get_session() as s:
            u = get_or_create_user_by_tid(s, q.from_user.id)
            kws = list_keywords(u.id)
            row = s.execute(text(
                "SELECT countries, proposal_template, trial_start, trial_end, license_until, is_active, is_blocked "
                "FROM \"user\" WHERE id=:id"), {"id": u.id}).fetchone()
        txt = settings_text(kws, row[0] or "ALL", row[1], row[2], row[3], row[4], bool(row[5]), bool(row[6]))
        await q.message.reply_text(txt, parse_mode=ParseMode.HTML, disable_web_page_preview=True); await q.answer(); return

    if data == "act:help":
        await q.message.reply_text(HELP_EN + help_footer(STATS_WINDOW_HOURS),
                                   parse_mode=ParseMode.HTML, disable_web_page_preview=True); await q.answer(); return

    if data == "act:saved":
        await q.message.reply_text("Saved list: (demo)"); await q.answer(); return

    if data == "act:contact":
        await q.message.reply_text(
            "Send a message for the admin. After they tap Reply, this becomes a continuous chat.\n"
            "Type /done to exit keyword entry; /endchat to end the pairing."
        ); await q.answer(); return

    if data == "act:admin":
        if not is_admin_user(q.from_user.id):
            await q.answer("Not allowed", show_alert=True); return
        await q.message.reply_text(
            "<b>Admin panel</b>\n"
            "<code>/users</code> — list users\n"
            "<code>/grant &lt;id&gt; &lt;days&gt;</code>\n"
            "<code>/block &lt;id&gt;</code> / <code>/unblock &lt;id&gt;</code>\n"
            "<code>/broadcast &lt;text&gt;</code>\n"
            "<code>/feedstatus</code> — per-platform stats\n"
            "<code>/endchat</code> — end current chat pairing",
            parse_mode=ParseMode.HTML,
        ); await q.answer(); return

    await q.answer()

async def admin_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin_user(q.from_user.id):
        await q.answer("Not allowed", show_alert=True); return
    parts = (q.data or "").split(":")  # adm:reply:<uid> | adm:grant:<uid>:<days> | adm:decline:<uid>
    if len(parts) < 3 or parts[0] != "adm":
        await q.answer(); return
    action, target = parts[1], int(parts[2])

    if action == "reply":
        pair_admin_user(context.application, q.from_user.id, target)
        await q.message.reply_text(f"Replying to <code>{target}</code>. Type your messages. Use /endchat to stop.",
                                   parse_mode=ParseMode.HTML); await q.answer(); return
    if action == "decline":
        unpair_admin_user(context.application, user_id=target)
        try: await context.bot.send_message(chat_id=target, text="Your message was received. The admin declined to reply.")
        except Exception: pass
        await q.answer("Declined"); return
    if action == "grant":
        days = int(parts[3]) if len(parts) >= 4 else 30
        until = datetime.now(timezone.utc) + timedelta(days=days)
        with get_session() as s:
            s.execute(text("UPDATE \"user\" SET license_until=:dt WHERE telegram_id=:tid"),
                      {"dt": until, "tid": target}); s.commit()
        try: await context.bot.send_message(chat_id=target, text=f"🔑 Your access is extended until {until.strftime('%Y-%m-%d %H:%M UTC')}.")
        except Exception: pass
        await q.answer(f"Granted +{days}d"); return
    await q.answer()

async def job_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.data == "job:save":
        await q.message.reply_text("Saved ⭐"); await q.answer(); return
    if q.data == "job:delete":
        await q.message.reply_text("Deleted 🗑"); await q.answer(); return
    await q.answer()

# ============= Text router (keywords inline + contact) =============
async def incoming_message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text or update.message.text.startswith("/"):
        return
    app = context.application
    uid = update.effective_user.id
    text_msg = update.message.text.strip()

    if app and app.bot_data.get("start_fallback_on_first_update"):
        await _ensure_fallback_running(app)
        app.bot_data.pop("start_fallback_on_first_update", None)

    # Inline keywords mode (μένει on μέχρι /done ή /cancel)
    if context.user_data.get("awaiting_keywords"):
        if text_msg.lower() in {"/done", "done", "/cancel", "cancel"}:
            context.user_data["awaiting_keywords"] = False
            await update.message.reply_text("Keyword entry finished."); return
        await _add_keywords_flow(update, context, text_msg)
        context.user_data["awaiting_keywords"] = True
        return

    # Continuous chat routing
    if is_admin_user(uid):
        target = get_paired_user(app, uid)
        if target:
            try: await context.bot.send_message(chat_id=target, text=f"💬 Admin: {text_msg}")
            except Exception: await update.message.reply_text("Failed to deliver.")
            return
    adm = get_paired_admin(app, uid)
    if adm:
        try:
            await context.bot.send_message(chat_id=adm, text=f"✉️ From {uid}:\n\n{text_msg}",
                                           reply_markup=admin_contact_kb(uid))
        except Exception: pass
        return

    # No pair yet → forward to all admins
    admins = all_admin_ids()
    if not admins:
        await update.message.reply_text("No admin is available at the moment."); return
    for aid in admins:
        try:
            await context.bot.send_message(
                chat_id=aid,
                text=f"✉️ <b>New message from user</b>\nID: <code>{uid}</code>\n\n{text_msg}",
                parse_mode=ParseMode.HTML,
                reply_markup=admin_contact_kb(uid),
            )
        except Exception:
            pass
    await update.message.reply_text("Thanks! Your message was forwarded to the admin 👌")

# ============= Shared: add keywords flow =============
async def _add_keywords_flow(update: Update, context: ContextTypes.DEFAULT_TYPE, raw: str):
    kws = parse_keywords(raw)
    if not kws:
        await update.effective_chat.send_message("No valid keywords were provided.", parse_mode=ParseMode.HTML); return
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
    try:
        inserted = add_keywords(u.id, kws)  # direct SQL into column `keyword`
    except Exception as e:
        await update.effective_chat.send_message(f"Keyword insert failed: {e}"); return
    current = list_keywords(u.id)
    msg = f"✅ Added {inserted} new keyword(s)." if inserted > 0 else "ℹ️ Those keywords already exist (no changes)."
    await update.effective_chat.send_message(msg + "\n\nCurrent keywords:\n• " + (", ".join(current) if current else "—"),
                                             parse_mode=ParseMode.HTML)

# ============= Expiry reminders =============
async def notify_expiring_job(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(timezone.utc)
    soon = now + timedelta(hours=24)
    with get_session() as s:
        rows = s.execute(text(
            "SELECT telegram_id, COALESCE(license_until, trial_end) AS exp "
            "FROM \"user\" WHERE is_active=TRUE AND is_blocked=FALSE"
        )).fetchall()
    for tid, expiry in rows:
        if not expiry:
            continue
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if now < expiry <= soon:
            try:
                hours_left = int((expiry - now).total_seconds() // 3600)
                await context.bot.send_message(chat_id=tid,
                    text=f"⏰ Reminder: your access expires in about {hours_left} hours (on {expiry.strftime('%Y-%m-%d %H:%M UTC')}).")
            except Exception:
                pass

async def _background_expiry_loop(app: Application):
    await asyncio.sleep(5)
    while True:
        try:
            ctx = SimpleNamespace(bot=app.bot)
            await notify_expiring_job(ctx)  # type: ignore[arg-type]
        except Exception as e:
            log.exception("expiry loop error: %s", e)
        await asyncio.sleep(3600)

async def _ensure_fallback_running(app: Application):
    if app.bot_data.get("expiry_task"): return
    try:
        app.bot_data["expiry_task"] = asyncio.get_event_loop().create_task(_background_expiry_loop(app))
        log.info("Fallback expiry loop started (immediate).")
    except Exception as e:
        log.warning("Could not start fallback loop immediately: %s", e)

# ============= Build app =============
def build_application() -> Application:
    ensure_schema()
    ensure_feed_events_schema()  # δημιουργεί feed_events αν λείπει

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # public
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("whoami", whoami_cmd))
    app.add_handler(CommandHandler("sudo", sudo_cmd))
    app.add_handler(CommandHandler("endchat", endchat_cmd))
    app.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app.add_handler(CommandHandler("keywords", keywords_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))
    app.add_handler(CommandHandler("selftest", selftest_cmd))

    # admin
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CommandHandler("grant", grant_cmd))
    app.add_handler(CommandHandler("block", block_cmd))
    app.add_handler(CommandHandler("unblock", unblock_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("feedstatus", feedstatus_cmd))
    app.add_handler(CommandHandler("feetstatus", feedstatus_cmd))  # alias

    # callbacks
    app.add_handler(CallbackQueryHandler(menu_action_cb, pattern=r"^act:(addkw|settings|help|saved|contact|admin)$"))
    app.add_handler(CallbackQueryHandler(admin_action_cb, pattern=r"^adm:(reply|decline|grant):"))
    app.add_handler(CallbackQueryHandler(job_action_cb, pattern=r"^job:(save|delete)$"))

    # text router
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, incoming_message_router))

    # scheduler
    used_jobqueue = False
    try:
        if JobQueue is not None:
            jq = app.job_queue or JobQueue()
            if app.job_queue is None:
                jq.set_application(app)
            jq.run_repeating(notify_expiring_job, interval=3600, first=60)  # type: ignore[arg-type]
            used_jobqueue = True
            log.info("Scheduler: JobQueue")
    except Exception as e:
        log.warning("JobQueue unavailable (%s). Using fallback.", e)

    if not used_jobqueue:
        try:
            app.bot_data["expiry_task"] = asyncio.get_event_loop().create_task(_background_expiry_loop(app))
            log.info("Scheduler: fallback loop (started immediately)")
        except Exception:
            app.bot_data["start_fallback_on_first_update"] = True
            log.info("Scheduler: fallback loop (will start on first update)")

    log.info("Handlers ready (scheduler=%s)", "jobqueue" if used_jobqueue else "fallback")
    return app
