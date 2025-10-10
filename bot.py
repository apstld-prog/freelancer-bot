# bot.py — Welcome layout όπως στη Φωτο 1 + σταθερά callbacks
import os, logging, asyncio, json
from datetime import datetime, timedelta, timezone
from typing import List, Set, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)
from sqlalchemy import text

from db import ensure_schema, get_session, get_or_create_user_by_tid
from config import ADMIN_IDS, TRIAL_DAYS, STATS_WINDOW_HOURS
from db_events import ensure_feed_events_schema, get_platform_stats
from db_keywords import (
    list_keywords, add_keywords, count_keywords,
    ensure_keyword_unique, delete_keywords, clear_keywords
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN env var is required")

# ---------- helpers ----------
def all_admin_ids() -> Set[int]:
    ids = set(int(x) for x in (ADMIN_IDS or []))
    try:
        with get_session() as s:
            rows = s.execute(text('SELECT telegram_id FROM "user" WHERE is_admin=TRUE')).fetchall()
        ids |= {int(r[0]) for r in rows if r[0]}
    except Exception:
        pass
    return ids

def is_admin_user(tid: int) -> bool:
    return tid in all_admin_ids()

def main_menu_kb(is_admin: bool=False) -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("➕ Add Keywords", callback_data="act:addkw"),
         InlineKeyboardButton("⚙️ Settings", callback_data="act:settings")],
        [InlineKeyboardButton("🆘 Help", callback_data="act:help"),
         InlineKeyboardButton("💾 Saved", callback_data="act:saved")],
        [InlineKeyboardButton("📨 Contact", callback_data="act:contact")],
    ]
    if is_admin: kb.append([InlineKeyboardButton("🔥 Admin", callback_data="act:admin")])
    return InlineKeyboardMarkup(kb)

FEATURES_EN = (
    "✨ <b>Features</b>\n"
    "• Real-time job alerts (Freelancer API)\n"
    "• Affiliate-wrapped <b>Proposal</b> & <b>Original</b> links\n"
    "• Budget shown + USD conversion\n"
    "• ⭐ Keep / 🗑 Delete buttons\n"
    "• 10-day free trial (extend via admin)\n"
    "• Multi-keyword search (single/all modes)\n"
    "• Platforms by country (incl. GR boards)"
)

HELP_EN = (
    "<b>🧭 Help / How it works</b>\n\n"
    "<b>Add keywords</b> with <code>/addkeyword logo, lighting</code>\n"
    "Remove with <code>/delkeyword logo</code> • Clear: <code>/clearkeywords</code>\n\n"
    "Use <code>/mysettings</code> anytime."
)

def settings_text(keywords: List[str], countries: str|None, proposal_template: str|None,
                  trial_start, trial_end, license_until, active: bool, blocked: bool) -> str:
    def b(v: bool) -> str: return "✅" if v else "❌"
    k = ", ".join(keywords) if keywords else "(none)"
    c = countries if countries else "ALL"
    pt = "(none)" if not proposal_template else "(saved)"
    ts = trial_start.isoformat().replace("+00:00","Z") if trial_start else "—"
    te = trial_end.isoformat().replace("+00:00","Z") if trial_end else "—"
    lic = "None" if not license_until else license_until.isoformat().replace("+00:00","Z")
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

# ---------- /start (πληκτρολόγιο στο ΙΔΙΟ μήνυμα) ----------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    with get_session() as s:
        usr = get_or_create_user_by_tid(s, u.id)
        s.execute(text('UPDATE "user" SET trial_start=COALESCE(trial_start, NOW() AT TIME ZONE \'UTC\') WHERE id=:id'),
                  {"id": usr.id})
        s.execute(
            text("UPDATE \"user\" SET trial_end=COALESCE(trial_end, (NOW() AT TIME ZONE 'UTC') + INTERVAL :d) WHERE id=:id")
            .bindparams(d=f"{TRIAL_DAYS} days"),
            {"id": usr.id},
        )
        expiry = s.execute(text('SELECT COALESCE(license_until, trial_end) FROM "user" WHERE id=:id'),
                           {"id": usr.id}).scalar()
        s.commit()

    first = (
        "<b>👋 Welcome to Freelancer Alert Bot!</b>\n\n"
        "🎁 You have a <b>10-day free trial</b>.\n"
        "The bot finds matching freelance jobs from top platforms and sends instant alerts.\n"
        f"<b>Free trial ends:</b> {expiry.strftime('%Y-%m-%d %H:%M UTC') if isinstance(expiry, datetime) else '—'}\n\n"
        "Use <code>/help</code> for instructions."
    )
    # ⬇️ Κουμπιά στο ΙΔΙΟ μήνυμα
    await update.effective_chat.send_message(
        first,
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_kb(is_admin=is_admin_user(u.id))
    )
    # Δεύτερο μήνυμα: Features block
    await update.effective_chat.send_message(FEATURES_EN, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

# ---------- settings/help ----------
async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        kws = list_keywords(u.id)
        row = s.execute(text('SELECT countries, proposal_template, trial_start, trial_end, license_until, is_active, is_blocked FROM "user" WHERE id=:id'),
                        {"id": u.id}).fetchone()
    txt = settings_text(kws, row[0], row[1], row[2], row[3], row[4], bool(row[5]), bool(row[6]))
    await update.message.reply_text(txt, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(HELP_EN, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

# ---------- keywords ----------
def _parse_keywords(raw: str) -> List[str]:
    parts = [p.strip() for chunk in raw split(",") for p in chunk.split() if p.strip()]
    seen, out = set(), []
    for p in parts:
        lp = p.lower()
        if lp not in seen:
            seen.add(lp); out.append(p)
    return out

async def addkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Add keywords separated by commas. Example:\n<code>/addkeyword logo, lighting</code>",
            parse_mode=ParseMode.HTML
        ); return
    kws = _parse_keywords(" ".join(context.args))
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
    n = add_keywords(u.id, kws)
    cur = list_keywords(u.id)
    msg = "✅ Added." if n else "ℹ️ Those keywords already exist (no changes)."
    await update.message.reply_text(msg + "\n\nCurrent keywords:\n• " + (", ".join(cur) if cur else "—"),
                                    parse_mode=ParseMode.HTML)

async def delkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Delete keywords. Example:\n<code>/delkeyword logo, sales</code>",
                                        parse_mode=ParseMode.HTML); return
    kws = _parse_keywords(" ".join(context.args))
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
    n = delete_keywords(u.id, kws)
    left = list_keywords(u.id)
    await update.message.reply_text(f"🗑 Removed {n}.\n\nCurrent keywords:\n• " + (", ".join(left) if left else "—"),
                                    parse_mode=ParseMode.HTML)

async def clearkeywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Yes, clear all", callback_data="kw:clear:yes"),
                                InlineKeyboardButton("❌ No", callback_data="kw:clear:no")]])
    await update.message.reply_text("Clear ALL your keywords?", reply_markup=kb)

# ---------- admin ----------
async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        await update.message.reply_text("You are not an admin."); return
    with get_session() as s:
        rows = s.execute(text('SELECT id, telegram_id, trial_end, license_until, is_active, is_blocked FROM "user" ORDER BY id DESC LIMIT 200')).fetchall()
    lines = ["<b>Users</b>"]
    for uid, tid, trial_end, lic, act, blk in rows:
        kwc = count_keywords(uid)
        lines.append(f"• <a href=\"tg://user?id={tid}\">{tid}</a> — kw:{kwc} | trial:{trial_end} | lic:{lic} | A:{'✅' if act else '❌'} B:{'✅' if blk else '❌'}")
    await update.effective_chat.send_message("\n".join(lines), parse_mode=ParseMode.HTML)

async def feedstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id): return
    try:
        stats = get_platform_stats(STATS_WINDOW_HOURS) or {}
    except Exception as e:
        await update.effective_chat.send_message(f"Feed status unavailable: {e}"); return
    if not stats:
        await update.effective_chat.send_message(f"No events in the last {STATS_WINDOW_HOURS} hours."); return
    await update.effective_chat.send_message("📊 Feed status (last %dh):\n%s" % (
        STATS_WINDOW_HOURS, "\n".join([f"• {k}: {v}" for k,v in stats.items()])
    ))

async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    role = "🧩 Admin" if is_admin_user(tid) else "👤 User"
    await update.message.reply_text(f"<b>Role:</b> {role}\n<b>Telegram ID:</b> <code>{tid}</code>",
                                    parse_mode=ParseMode.HTML)

# ---------- callbacks ----------
async def menu_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; data = (q.data or "").strip()
    if data == "act:addkw":
        await q.answer()
        return await q.message.reply_text(
            "Add keywords with:\n<code>/addkeyword logo, lighting</code>\n"
            "Remove: <code>/delkeyword logo</code> • Clear: <code>/clearkeywords</code>",
            parse_mode=ParseMode.HTML)
    if data == "act:settings":
        with get_session() as s:
            u = get_or_create_user_by_tid(s, q.from_user.id)
            kws = list_keywords(u.id)
            row = s.execute(text('SELECT countries, proposal_template, trial_start, trial_end, license_until, is_active, is_blocked FROM "user" WHERE id=:id'),
                            {"id": u.id}).fetchone()
        await q.answer()
        return await q.message.reply_text(settings_text(kws, row[0], row[1], row[2], row[3], row[4], bool(row[5]), bool(row[6])),
                                          parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    if data == "act:help":
        await q.answer(); return await q.message.reply_text(HELP_EN, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    if data == "act:saved":
        await q.answer(); return await q.message.reply_text("Opening Saved… use /saved soon (under construction).")
    if data == "act:contact":
        await q.answer(); return await q.message.reply_text("Send your message here; it will be forwarded to the admin.")
    if data == "act:admin":
        await q.answer()
        if not is_admin_user(q.from_user.id): return await q.message.reply_text("Not allowed.")
        return await q.message.reply_text(
            "<b>Admin panel</b>\n"
            "<code>/users</code> • <code>/grant &lt;id&gt; &lt;days&gt;</code>\n"
            "<code>/block &lt;id&gt;</code> • <code>/unblock &lt;id&gt;</code>\n"
            "<code>/broadcast &lt;text&gt;</code> • <code>/feedstatus</code>",
            parse_mode=ParseMode.HTML)

async def kw_clear_confirm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q.data.startswith("kw:clear:"): return await q.answer()
    if q.data.endswith(":no"):
        await q.answer(); return await q.message.reply_text("Cancelled.")
    with get_session() as s:
        u = get_or_create_user_by_tid(s, q.from_user.id)
    n = clear_keywords(u.id)
    await q.answer(); return await q.message.reply_text(f"🗑 Cleared {n} keyword(s).")

# ---------- wiring ----------
def build_application() -> Application:
    ensure_schema()
    ensure_feed_events_schema()
    ensure_keyword_unique()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))
    app.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app.add_handler(CommandHandler("delkeyword", delkeyword_cmd))
    app.add_handler(CommandHandler("clearkeywords", clearkeywords_cmd))
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CommandHandler("feedstatus", feedstatus_cmd))
    app.add_handler(CommandHandler("whoami", whoami_cmd))

    app.add_handler(CallbackQueryHandler(menu_action_cb, pattern=r"^act:(addkw|settings|help|saved|contact|admin)$"))
    app.add_handler(CallbackQueryHandler(kw_clear_confirm_cb, pattern=r"^kw:clear:(yes|no)$"))

    return app
