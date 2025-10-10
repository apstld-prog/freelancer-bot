
from __future__ import annotations
import logging, urllib.parse
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, Application,
    CommandHandler, CallbackQueryHandler,
    ContextTypes,
    JobQueue
)
from sqlalchemy import text

from config import BOT_TOKEN, ADMIN_IDS, STATS_WINDOW_HOURS, TRIAL_DAYS
from db import get_session, ensure_schema, get_or_create_user_by_tid
from db_events import ensure_feed_events_schema, get_platform_stats
from db_saved import ensure_saved_schema, add_saved_job, list_saved_jobs, clear_saved_jobs
from db_trial_notice import ensure_trial_notice_schema, has_day_before_sent, mark_day_before_sent

log = logging.getLogger("bot")
logging.basicConfig(level=logging.INFO)

try:
    from db import ensure_keyword_unique  # type: ignore
except Exception:
    def ensure_keyword_unique():
        log.warning("ensure_keyword_unique() not found in db.py — skipping")

def is_admin_user(tid: int) -> bool:
    try:
        return int(tid) in ADMIN_IDS
    except Exception:
        return False

from sqlalchemy import text as _t

def _kwexpr() -> str:
    return 'COALESCE(keyword, value)'

def list_keywords_safe(user_id: int) -> List[str]:
    with get_session() as s:
        rows = s.execute(_t(f'SELECT {_kwexpr()} FROM "keyword" WHERE user_id=:u ORDER BY id ASC'), {"u": user_id}).fetchall()
        return [r[0] for r in rows if r and r[0]]

def add_keywords_safe(user_id: int, values: List[str]):
    added, skipped = [], []
    if not values: return 0, added, skipped
    with get_session() as s:
        for v in values:
            vv = (v or "").strip()
            if not vv:
                continue
            ex = s.execute(_t('SELECT 1 FROM "keyword" WHERE user_id=:u AND (keyword=:v OR value=:v) LIMIT 1'),
                           {"u": user_id, "v": vv}).fetchone()
            if ex:
                skipped.append(vv); continue
            s.execute(_t('INSERT INTO "keyword"(user_id, keyword, value, created_at) '
                         "VALUES (:u, :v, :v, NOW() AT TIME ZONE 'UTC')"),
                      {"u": user_id, "v": vv})
            added.append(vv)
        if added: s.commit()
    return len(added), added, skipped

def delete_keyword_safe(user_id: int, value: str) -> bool:
    with get_session() as s:
        rc = s.execute(_t('DELETE FROM "keyword" WHERE user_id=:u AND (keyword=:v OR value=:v)'),
                       {"u": user_id, "v": value}).rowcount
        if rc: s.commit()
    return rc > 0

def clear_keywords_safe(user_id: int) -> int:
    with get_session() as s:
        rc = s.execute(_t('DELETE FROM "keyword" WHERE user_id=:u'), {"u": user_id}).rowcount
        if rc: s.commit()
    return int(rc or 0)

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

def settings_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗂 List keywords", callback_data="kw:list")],
        [InlineKeyboardButton("🧹 Clear all keywords", callback_data="kw:clear")],
        [InlineKeyboardButton("⬅️ Back", callback_data="act:back")],
    ])

def fmt_dt(dt: Optional[datetime]) -> str:
    if not dt:
        return "-"
    if isinstance(dt, datetime):
        return dt.isoformat()
    return str(dt)

def welcome_text(trial_start: Optional[datetime], trial_end: Optional[datetime]) -> str:
    return (
        "<b>Welcome to Freelancer Alert Bot!</b>\n"
        f"• Trial start: {fmt_dt(trial_start)}\n"
        f"• Trial end: {fmt_dt(trial_end)}\n"
        "Use /addkeyword to add search keywords."
    )

# ---------- Commands ----------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        try:
            s.execute(_t("UPDATE \"user\" SET is_active=TRUE WHERE id=:id"), {"id": u.id})
            s.execute(_t("UPDATE \"user\" SET trial_start=COALESCE(trial_start, NOW() AT TIME ZONE 'UTC') WHERE id=:id"), {"id": u.id})
            s.execute(_t("UPDATE \"user\" SET trial_end=COALESCE(trial_end, NOW() AT TIME ZONE 'UTC') + INTERVAL :days WHERE id=:id")
                      .bindparams(days=f"{TRIAL_DAYS} days"), {"id": u.id})
            row = s.execute(_t('SELECT trial_start, trial_end FROM "user" WHERE id=:id'), {"id": u.id}).fetchone()
            s.commit()
            trial_start, trial_end = (row[0], row[1]) if row else (None, None)
        except Exception:
            logging.getLogger("bot").exception("start_cmd: trial init failed")
            trial_start = trial_end = None

    await update.effective_chat.send_message(
        welcome_text(trial_start, trial_end),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_kb(is_admin=is_admin_user(update.effective_user.id)),
        disable_web_page_preview=True,
    )
    await help_cmd(update, context)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = [
        "<b>Help / How it works</b>",
        "1) Add keywords with <code>/addkeyword python, telegram</code> (English or Greek).",
        "2) Check your settings with <code>/mysettings</code>.",
        "3) Use <code>/selftest</code> to see a sample alert.",
        "",
        "Use <code>/whoami</code> to see your trial dates and keywords.",
    ]
    if is_admin_user(update.effective_user.id):
        lines += [
            "",
            "👑 <b>Admin commands</b>:",
            "/users — list users",
            "/feedstatus — last 24h by platform",
            "/grant <telegram_id> <days> — extend license",
            "/block <telegram_id> / /unblock <telegram_id>",
            "/broadcast <text> — to all active",
        ]
    await update.effective_chat.send_message(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )

async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        row = s.execute(_t('SELECT is_active, trial_start, trial_end, license_until FROM "user" WHERE id=:id'), {"id": u.id}).fetchone()
    is_admin = "yes" if is_admin_user(update.effective_user.id) else "no"
    is_active = "yes" if (row and row[0]) else "no"
    trial_start = row[1] if row else None
    trial_end = row[2] if row else None
    lic_until = row[3] if row else None
    kws = list_keywords_safe(u.id)
    txt = (
        "<b>Who am I</b>\n"
        f"• Telegram ID: <code>{update.effective_user.id}</code>\n"
        f"• Admin: <b>{is_admin}</b>\n"
        f"• Active: <b>{is_active}</b>\n"
        f"• Trial start: {fmt_dt(trial_start)}\n"
        f"• Trial end: {fmt_dt(trial_end)}\n"
        f"• License until: {fmt_dt(lic_until)}\n"
        f"• Keywords: {', '.join(kws) if kws else '(none)'}"
    )
    await update.effective_chat.send_message(txt, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

def _parse_kw_args(text: str) -> List[str]:
    if not text: return []
    txt = text.replace(";", ",").replace("  ", " ")
    parts = [p.strip() for p in txt.split(",") if p.strip()]
    if not parts:
        parts = [p.strip() for p in txt.split() if p.strip()]
    seen, out = set(), []
    for p in parts:
        if p not in seen:
            seen.add(p); out.append(p)
    return out

async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        user = get_or_create_user_by_tid(s, update.effective_user.id)
    kws = list_keywords_safe(user.id)
    kw_str = ", ".join(kws) if kws else "(none)"
    await update.effective_chat.send_message(
        f"<b>Your Settings</b>\n• <b>Keywords:</b> {kw_str}\n\nUsage: /addkeyword word1, word2.\nYou can also use the buttons below.",
        parse_mode=ParseMode.HTML,
        reply_markup=settings_kb(),
        disable_web_page_preview=True,
    )

async def addkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.effective_message.text or ""
    raw = raw.partition(" ")[2]
    kws = _parse_kw_args(raw)
    if not kws:
        await update.message.reply_text("Usage: /addkeyword word1, word2")
        return
    with get_session() as s:
        user = get_or_create_user_by_tid(s, update.effective_user.id)
    n, added, skipped = add_keywords_safe(user.id, kws)
    msg = f"✅ Added: {', '.join(added)}" if added else "—"
    if skipped:
        msg += f"\n↪️ Already existed: {', '.join(skipped)}"
    await update.message.reply_text(msg)

async def delkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.effective_message.text or ""
    arg = raw.partition(" ")[2].strip()
    if not arg:
        await update.message.reply_text("Usage: /delkeyword word")
        return
    with get_session() as s:
        user = get_or_create_user_by_tid(s, update.effective_user.id)
    ok = delete_keyword_safe(user.id, arg)
    await update.message.reply_text("Deleted." if ok else "Not found.")

async def clearkeywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        user = get_or_create_user_by_tid(s, update.effective_user.id)
    n = clear_keywords_safe(user.id)
    await update.message.reply_text(f"Cleared {n} keywords.")

async def selftest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    job_title = "Email Signature from Existing Logo"
    budget_min = 10.0
    budget_max = 30.0
    source = "PeoplePerHour"
    match_url = "https://www.peopleperhour.com/freelance-jobs?q=logo"
    description = "Please duplicate and make an editable version of my existing email signature based on the logo file"
    job_text = (
        f"<b>{job_title}</b>\n"
        f"  <b>Budget:</b> {budget_min:.1f}–{budget_max:.1f}\n"
        f"  <b>Source:</b> {source}\n"
        f"  <b>🔎 Match:</b> <a href=\"{match_url}\">logo</a>\n"
        f"  <b>📝</b> {description}"
    )
    url = "https://www.peopleperhour.com/freelance-jobs/technology-programming/other/"
    payload = urllib.parse.quote_plus(f"{job_title}|{url}")
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📄 Proposal", url=url),
        InlineKeyboardButton("🔗 Original", url=url)
    ],[
        InlineKeyboardButton("⭐ Save", callback_data=f"job:save|{payload}"),
        InlineKeyboardButton("🗑️ Delete", callback_data="job:delete")
    ]])
    await update.effective_chat.send_message(
        job_text, parse_mode=ParseMode.HTML, reply_markup=kb, disable_web_page_preview=True
    )

async def cb_mainmenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; data = q.data if q else ""
    await q.answer()
    if data == "act:addkw":
        await q.message.reply_text("Send: /addkeyword word1, word2")
    elif data == "act:settings":
        await mysettings_cmd(update, context)
    elif data == "act:saved":
        with get_session() as s:
            user = get_or_create_user_by_tid(s, update.effective_user.id)
        rows = list_saved_jobs(user.id, 25)
        if not rows:
            await q.message.reply_text("No saved jobs yet.")
            return
        lines = ["<b>Saved jobs</b>"]
        for sid, title, url, desc, created in rows:
            safe_title = (title or "(no title)")
            lines.append(f"• <a href=\"{url or '#'}\">{safe_title}</a>")
        await q.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    elif data == "act:help":
        await help_cmd(update, context)
    elif data == "act:contact":
        await q.message.reply_text("Contact: @your_username")
    elif data == "act:admin":
        if is_admin_user(update.effective_user.id):
            await q.message.reply_text(
                "Admin commands:\n"
                "/users — list users\n"
                "/feedstatus — last 24h by platform\n"
                "/grant <telegram_id> <days> — extend license\n"
                "/block <telegram_id> / /unblock <telegram_id>\n"
                "/broadcast <text> — to all active",
                disable_web_page_preview=True
            )
        else:
            await q.message.reply_text("You're not an admin.")
    elif data == "act:back":
        await q.message.reply_text("Back to main menu.", reply_markup=main_menu_kb(is_admin=is_admin_user(update.effective_user.id)))
    elif data == "kw:list":
        with get_session() as s:
            user = get_or_create_user_by_tid(s, update.effective_user.id)
        kws = list_keywords_safe(user.id)
        await q.message.reply_text("Keywords: " + (", ".join(kws) if kws else "(none)"))
    elif data == "kw:clear":
        with get_session() as s:
            user = get_or_create_user_by_tid(s, update.effective_user.id)
        n = clear_keywords_safe(user.id)
        await q.message.reply_text(f"Cleared {n} keywords.")
    else:
        await q.message.reply_text("Unknown action.")

async def cb_job(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data or ""
    if data.startswith("job:save"):
        payload = ""
        if "|" in data:
            payload = data.split("|", 1)[1]
        title, url = "(saved job)", ""
        if payload:
            try:
                dec = urllib.parse.unquote_plus(payload)
                parts = dec.split("|", 1)
                title = parts[0].strip() or title
                url = parts[1].strip() if len(parts) > 1 else url
            except Exception:
                pass
        with get_session() as s:
            user = get_or_create_user_by_tid(s, update.effective_user.id)
        add_saved_job(user.id, title, url, "")
        await q.answer("Saved ⭐", show_alert=False)
        try:
            await q.message.delete()
        except Exception:
            pass
    elif data == "job:delete":
        await q.answer("Deleted 🗑️", show_alert=False)
        try:
            await q.message.delete()
        except Exception:
            pass
    else:
        await q.answer("Unknown action", show_alert=False)

async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        await update.message.reply_text("You're not an admin."); return
    with get_session() as s:
        rows = s.execute(text('SELECT id, telegram_id, trial_end, license_until, is_active, is_blocked FROM "user" ORDER BY id DESC LIMIT 200')).fetchall()
    lines = ["<b>Users</b>"]
    for uid, tid, trial_end, lic, act, blk in rows:
        kwc = len(list_keywords_safe(uid))
        lines.append(f"• <a href=\"tg://user?id={tid}\">{tid}</a> — kw:{kwc} | trial:{trial_end or '-'} | lic:{lic or '-'} | active:{'Y' if act else 'N'} | blocked:{'Y' if blk else 'N'}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML, disable_web_page_preview=True)

async def feedstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        await update.message.reply_text("You're not an admin."); 
        return
    stats = get_platform_stats(STATS_WINDOW_HOURS) or {}
    if not stats:
        await update.effective_chat.send_message(f"No events in the last {STATS_WINDOW_HOURS} hours."); return
    await update.effective_chat.send_message("📊 Feed status (last %dh):\n%s" % (STATS_WINDOW_HOURS, "\n".join([f"• {k}: {v}" for k, v in stats.items()])))

# ---------- Scheduler: notify 1 day before trial end ----------
async def job_notify_trial_expiring(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(timezone.utc)
    in_24h = now + timedelta(hours=24)
    in_25h = now + timedelta(hours=25)
    with get_session() as s:
        rows = s.execute(_t('''
            SELECT id, telegram_id, trial_end
            FROM "user"
            WHERE is_active = TRUE
              AND trial_end IS NOT NULL
              AND trial_end >= :t1 AND trial_end < :t2
        '''), {"t1": in_24h, "t2": in_25h}).fetchall()
    for uid, tid, trial_end in rows:
        if has_day_before_sent(uid):
            continue
        text_msg = (
            "<b>Heads up!</b> Your free trial ends in 24 hours.\n"
            f"• Trial end: {trial_end.isoformat()}\n"
            "Reply /contact if you need more time."
        )
        try:
            await context.bot.send_message(chat_id=tid, text=text_msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            mark_day_before_sent(uid)
        except Exception as e:
            log.warning("Failed to send trial notice to %s: %s", tid, e)

def _setup_schedules(app: Application):
    jq: JobQueue = app.job_queue
    jq.run_repeating(job_notify_trial_expiring, interval=3600, first=30)

def build_application() -> Application:
    ensure_schema(); ensure_feed_events_schema(); ensure_saved_schema(); ensure_trial_notice_schema(); ensure_keyword_unique()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    # Commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("whoami", whoami_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))
    app.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app.add_handler(CommandHandler("addkw", addkeyword_cmd))
    app.add_handler(CommandHandler("keywords", mysettings_cmd))
    app.add_handler(CommandHandler("delkeyword", delkeyword_cmd))
    app.add_handler(CommandHandler("clearkeywords", clearkeywords_cmd))
    app.add_handler(CommandHandler("selftest", selftest_cmd))
    # Admin
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CommandHandler("feedstatus", feedstatus_cmd))
    # Buttons
    app.add_handler(CallbackQueryHandler(cb_mainmenu, pattern="^(act:|kw:)"))
    app.add_handler(CallbackQueryHandler(cb_job, pattern="^job:"))
    # Schedules
    _setup_schedules(app)
    return app
