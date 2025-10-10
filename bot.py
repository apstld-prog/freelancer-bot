# bot.py — stable build: interval CAST fix, Saved list, save/delete, menus
import os, logging, asyncio, json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import List, Set, Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import RetryAfter, TimedOut, NetworkError
from telegram.ext import (
    ApplicationBuilder, Application, CommandHandler, CallbackQueryHandler,
    ContextTypes,
)
from sqlalchemy import text

from db import ensure_schema, get_session, get_or_create_user_by_tid
from config import ADMIN_IDS, TRIAL_DAYS, STATS_WINDOW_HOURS
from db_events import ensure_feed_events_schema, get_platform_stats

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN")
             or os.getenv("BOT_TOKEN")
             or os.getenv("TELEGRAM_TOKEN"))
if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN env var is required")

# ----------------- helpers -----------------
async def safe_send(chat, text, **kwargs):
    retries = 2
    for i in range(retries + 1):
        try:
            return await chat.send_message(text, **kwargs)
        except RetryAfter as e:
            if e.retry_after and e.retry_after > 30:
                raise
            await asyncio.sleep(max(1, int(e.retry_after or 1)))
        except (TimedOut, NetworkError):
            await asyncio.sleep(1 + i)
    return await chat.send_message(text, **kwargs)

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
    if is_admin:
        kb.append([InlineKeyboardButton("🔥 Admin", callback_data="act:admin")])
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

def _b(v: bool) -> str: return "✅" if v else "❌"

def settings_text(kws: List[str], countries: str|None, proposal_template: str|None,
                  trial_start, trial_end, license_until, active: bool, blocked: bool) -> str:
    k = ", ".join(kws) if kws else "(none)"
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
        f"<b>✅ Active:</b> {_b(active)}    <b>⛔ Blocked:</b> {_b(blocked)}\n\n"
        "<b>🛰 Platforms monitored:</b> Global & GR boards.\n"
        "<i>For extension, contact the admin.</i>"
    )

def _ago(dt):
    if not isinstance(dt, datetime): return ""
    if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
    s = int((datetime.now(timezone.utc)-dt).total_seconds())
    if s < 60: return f"{s}s ago"
    m = s//60
    if m < 60: return f"{m}m ago"
    h = m//60
    if h < 24: return f"{h}h ago"
    d = h//24
    return f"{d}d ago"

def _render_card(ev: Dict[str,Any], matched: List[str]) -> str:
    title = ev.get("title") or "(no title)"
    platform = ev.get("platform") or "Freelancer"
    desc = (ev.get("description") or "").strip().replace("\n"," ")
    if len(desc) > 220: desc = desc[:219].rstrip()+"…"
    budget_line = ""
    if ev.get("budget_amount") and ev.get("budget_currency"):
        amt = ev["budget_amount"]; cur = ev["budget_currency"]
        usd = ev.get("budget_usd")
        if usd: budget_line = f"<b>Budget:</b> {amt:g} {cur} (~${usd:g} USD)\n"
        else:   budget_line = f"<b>Budget:</b> {amt:g} {cur}\n"
    return (
        f"<b>{title}</b>\n"
        f"{budget_line}"
        f"<b>Source:</b> {platform}\n"
        f"<b>Match:</b> {', '.join(matched)}\n"
        f"✏️ {desc}\n"
        f"<i>{_ago(ev.get('created_at'))}</i>"
    ).strip()

def _card_kb(ev_id: int, url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Proposal", url=url),
         InlineKeyboardButton("🔗 Original", url=url)],
        [InlineKeyboardButton("⭐ Save", callback_data=f"job:save:{ev_id}"),
         InlineKeyboardButton("🗑️ Delete", callback_data="job:delete")]
    ])

# ----------------- schema for saved -----------------
def ensure_saved_schema():
    with get_session() as s:
        s.execute(text("""
            CREATE TABLE IF NOT EXISTS saved_job(
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                job_id BIGINT NOT NULL,
                payload JSONB,
                saved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(user_id, job_id)
            )
        """))
        s.commit()

# ----------------- /start -----------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    with get_session() as s:
        usr = get_or_create_user_by_tid(s, u.id)
        s.execute(
            text('UPDATE "user" SET trial_start=COALESCE(trial_start, NOW() AT TIME ZONE \'UTC\') WHERE id=:id'),
            {"id": usr.id}
        )
        s.execute(
            text(
                "UPDATE \"user\" "
                "SET trial_end = COALESCE("
                "    trial_end, "
                "    (NOW() AT TIME ZONE 'UTC') + (CAST(:d AS text) || ' days')::interval"
                ") "
                "WHERE id = :id"
            ),
            {"id": usr.id, "d": int(TRIAL_DAYS)},
        )
        expiry = s.execute(
            text('SELECT COALESCE(license_until, trial_end) FROM "user" WHERE id=:id'),
            {"id": usr.id}
        ).scalar()
        s.commit()

    first = (
        "<b>👋 Welcome to Freelancer Alert Bot!</b>\n\n"
        "🎁 You have a <b>10-day free trial</b>.\n"
        "The bot finds matching freelance jobs from top platforms and sends instant alerts.\n"
        f"<b>Free trial ends:</b> {expiry.strftime('%Y-%m-%d %H:%M UTC') if isinstance(expiry, datetime) else '—'}\n\n"
        "Use <code>/help</code> for instructions."
    )
    await safe_send(
        update.effective_chat,
        first,
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_kb(is_admin=is_admin_user(u.id))
    )
    await safe_send(update.effective_chat, FEATURES_EN, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

# ----------------- settings/help -----------------
async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        rows = s.execute(
            text("SELECT COALESCE(keyword,value) AS kw FROM keyword WHERE user_id=:u ORDER BY id"),
            {"u": u.id}
        ).all()
        kws = [r[0] for r in rows]
        row = s.execute(text(
            'SELECT countries, proposal_template, trial_start, trial_end, license_until, is_active, is_blocked '
            'FROM "user" WHERE id=:id'),
            {"id": u.id}
        ).fetchone()
    txt = settings_text(kws, row[0], row[1], row[2], row[3], row[4], bool(row[5]), bool(row[6]))
    await safe_send(update.effective_chat, txt, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await safe_send(update.effective_chat, HELP_EN, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

# ----------------- keywords (slash commands) -----------------
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
        return await safe_send(update.effective_chat,
            "Add keywords separated by commas. Example:\n<code>/addkeyword logo, lighting</code>",
            parse_mode=ParseMode.HTML)
    kws = _parse_keywords(" ".join(context.args))
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        added = 0
        for kw in kws:
            added += s.execute(text(
                "INSERT INTO keyword(user_id, keyword, created_at, updated_at) "
                "VALUES (:u, :k, NOW() AT TIME ZONE 'UTC', NOW() AT TIME ZONE 'UTC') "
                "ON CONFLICT DO NOTHING"), {"u": u.id, "k": kw}).rowcount or 0
        s.commit()
        cur = [r[0] for r in s.execute(text("SELECT keyword FROM keyword WHERE user_id=:u ORDER BY id"),
                                       {"u": u.id}).fetchall()]
    msg = "✅ Added." if added else "ℹ️ Those keywords already exist (no changes)."
    await safe_send(update.effective_chat, msg + "\n\nCurrent keywords:\n• " + (", ".join(cur) if cur else "—"),
                    parse_mode=ParseMode.HTML)

async def delkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await safe_send(update.effective_chat,
            "Delete keywords. Example:\n<code>/delkeyword logo, sales</code>",
            parse_mode=ParseMode.HTML)
    kws = _parse_keywords(" ".join(context.args))
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        n = s.execute(text("DELETE FROM keyword WHERE user_id=:u AND keyword = ANY(:ks)"),
                      {"u": u.id, "ks": kws}).rowcount or 0
        s.commit()
        left = [r[0] for r in s.execute(text("SELECT keyword FROM keyword WHERE user_id=:u ORDER BY id"),
                                        {"u": u.id}).fetchall()]
    await safe_send(update.effective_chat, f"🗑 Removed {n}.\n\nCurrent keywords:\n• " + (", ".join(left) if left else "—"),
                    parse_mode=ParseMode.HTML)

async def clearkeywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Yes, clear all", callback_data="kw:clear:yes"),
                                InlineKeyboardButton("❌ No", callback_data="kw:clear:no")]])
    await safe_send(update.effective_chat, "Clear ALL your keywords?", reply_markup=kb)

# ----------------- admin -----------------
async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id):
        return await safe_send(update.effective_chat, "You are not an admin.")
    with get_session() as s:
        rows = s.execute(text(
            'SELECT id, telegram_id, trial_end, license_until, is_active, is_blocked '
            'FROM "user" ORDER BY id DESC LIMIT 200'
        )).fetchall()
        lines = ["<b>Users</b>"]
        for uid, tid, trial_end, lic, act, blk in rows:
            kwc = s.execute(text("SELECT count(*) FROM keyword WHERE user_id=:u"), {"u": uid}).scalar() or 0
            lines.append(
                f"• <a href=\"tg://user?id={tid}\">{tid}</a> — kw:{kwc} | "
                f"trial:{trial_end} | lic:{lic} | A:{_b(bool(act))} B:{_b(bool(blk))}"
            )
    await safe_send(update.effective_chat, "\n".join(lines), parse_mode=ParseMode.HTML)

async def feedstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id): return
    try:
        stats = get_platform_stats(STATS_WINDOW_HOURS) or {}
    except Exception as e:
        return await safe_send(update.effective_chat, f"Feed status unavailable: {e}")
    if not stats:
        return await safe_send(update.effective_chat, f"No events in the last {STATS_WINDOW_HOURS} hours.")
    await safe_send(update.effective_chat,
                    "📊 Feed status (last %dh):\n%s" % (
                        STATS_WINDOW_HOURS, "\n".join([f"• {k}: {v}" for k,v in stats.items()])
                    ))

async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    role = "🧩 Admin" if is_admin_user(tid) else "👤 User"
    await safe_send(update.effective_chat,
                    f"<b>Role:</b> {role}\n<b>Telegram ID:</b> <code>{tid}</code>",
                    parse_mode=ParseMode.HTML)

# ----------------- job actions -----------------
async def job_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; data = (q.data or "").split(":")
    await q.answer()
    if len(data) < 2: return
    action = data[1]
    if action == "delete":
        try:
            await q.message.delete()
        except Exception:
            pass
        return
    if action == "save":
        job_id = int(data[2]) if len(data) > 2 and data[2].isdigit() else None
        if not job_id: return
        with get_session() as s:
            ev = s.execute(text("""
                SELECT id, platform, title, description, original_url, affiliate_url,
                       budget_amount, budget_currency, budget_usd, created_at
                FROM job_event WHERE id=:id
            """), {"id": job_id}).mappings().first()
            if ev:
                s.execute(text("""
                    INSERT INTO saved_job(user_id, job_id, payload)
                    VALUES (:u, :j, :p) ON CONFLICT DO NOTHING
                """), {"u": update.effective_user.id, "j": job_id, "p": json.dumps(dict(ev))})
                s.commit()
        try:
            await q.message.delete()
        except Exception:
            pass
        return

async def saved_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        rows = s.execute(text("""
            SELECT sj.job_id, sj.saved_at,
                   je.platform, je.title, je.description, je.affiliate_url, je.original_url,
                   je.budget_amount, je.budget_currency, je.budget_usd, je.created_at
            FROM saved_job sj
            LEFT JOIN job_event je ON je.id=sj.job_id
            WHERE sj.user_id=:u
            ORDER BY sj.saved_at DESC
            LIMIT 10
        """), {"u": update.effective_user.id}).mappings().all()
    if not rows:
        return await safe_send(update.effective_chat, "No saved jobs yet.")
    for r in rows:
        ev = dict(r)
        txt = _render_card(ev, matched=["saved"])
        url = ev.get("affiliate_url") or ev.get("original_url") or "#"
        kb = _card_kb(ev.get("job_id") or ev.get("id"), url)
        await safe_send(update.effective_chat, txt, parse_mode=ParseMode.HTML,
                        reply_markup=kb, disable_web_page_preview=True)

# ----------------- callbacks -----------------
async def menu_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; data = (q.data or "").strip()
    try:
        await q.answer()
        if data == "act:addkw":
            return await safe_send(q.message.chat,
                "Add keywords with:\n<code>/addkeyword logo, lighting</code>\n"
                "Remove: <code>/delkeyword logo</code> • Clear: <code>/clearkeywords</code>",
                parse_mode=ParseMode.HTML)
        if data == "act:settings":
            with get_session() as s:
                u = get_or_create_user_by_tid(s, q.from_user.id)
                rows = s.execute(text("SELECT keyword FROM keyword WHERE user_id=:u ORDER BY id"),
                                 {"u": u.id}).fetchall()
                kws = [r[0] for r in rows]
                row = s.execute(text(
                    'SELECT countries, proposal_template, trial_start, trial_end, license_until, is_active, is_blocked '
                    'FROM "user" WHERE id=:id'),
                    {"id": u.id}).fetchone()
            return await safe_send(q.message.chat,
                                   settings_text(kws, row[0], row[1], row[2], row[3], row[4],
                                                 bool(row[5]), bool(row[6])),
                                   parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        if data == "act:help":
            return await safe_send(q.message.chat, HELP_EN, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        if data == "act:saved":
            upd = SimpleNamespace(effective_user=q.from_user, effective_chat=q.message.chat)
            return await saved_cmd(upd, context)  # type: ignore
        if data == "act:contact":
            return await safe_send(q.message.chat, "Send your message here; it will be forwarded to the admin.")
        if data == "act:admin":
            if not is_admin_user(q.from_user.id):
                return await safe_send(q.message.chat, "Not allowed.")
            return await safe_send(
                q.message.chat,
                "<b>Admin panel</b>\n"
                "<code>/users</code> • <code>/grant &lt;id&gt; &lt;days&gt;</code>\n"
                "<code>/block &lt;id&gt;</code> • <code>/unblock &lt;id&gt;</code>\n"
                "<code>/broadcast &lt;text&gt;</code> • <code>/feedstatus</code>",
                parse_mode=ParseMode.HTML
            )
    except RetryAfter:
        await q.answer("Please wait a few seconds…", show_alert=False)

async def kw_clear_confirm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not q.data.startswith("kw:clear:"): return
    if q.data.endswith(":no"):
        return await safe_send(q.message.chat, "Cancelled.")
    with get_session() as s:
        u = get_or_create_user_by_tid(s, q.from_user.id)
        n = s.execute(text("DELETE FROM keyword WHERE user_id=:u"), {"u": u.id}).rowcount or 0
        s.commit()
    return await safe_send(q.message.chat, f"🗑 Cleared {n} keyword(s).")

# ----------------- wiring -----------------
def build_application() -> Application:
    ensure_schema()
    ensure_feed_events_schema()
    ensure_saved_schema()

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
    app.add_handler(CommandHandler("saved", saved_cmd))

    app.add_handler(CallbackQueryHandler(menu_action_cb,
                    pattern=r"^act:(addkw|settings|help|saved|contact|admin)$"))
    app.add_handler(CallbackQueryHandler(kw_clear_confirm_cb, pattern=r"^kw:clear:(yes|no)$"))
    app.add_handler(CallbackQueryHandler(job_action_cb, pattern=r"^job:(save|delete)(?::\d+)?$"))
    return app
