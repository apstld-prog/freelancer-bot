# bot.py — EN-only UI, USD budget, time-ago, save/delete, saved list as full cards
import os, logging, asyncio, json
from datetime import datetime, timedelta, timezone
from typing import List, Set, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)

try:
    from telegram.ext import JobQueue
except Exception:
    JobQueue = None  # type: ignore

from sqlalchemy import text
from db import ensure_schema, get_session, get_or_create_user_by_tid
from config import ADMIN_IDS, TRIAL_DAYS, STATS_WINDOW_HOURS
from db_events import ensure_feed_events_schema, get_platform_stats
from db_keywords import (
    list_keywords, add_keywords, count_keywords,
    ensure_keyword_unique, delete_keywords, clear_keywords
)

log = logging.getLogger("bot")
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN env var is required")

# ---------------- FX (EUR/GBP/... -> USD) ----------------
DEFAULT_RATES = {
    "USD": 1.0, "EUR": 1.07, "GBP": 1.24, "AUD": 0.65, "CAD": 0.73,
    "INR": 0.012, "BRL": 0.18, "TRY": 0.031,
}
def fx_rates():
    raw = os.getenv("FX_RATES_JSON", "")
    if not raw:
        return DEFAULT_RATES
    try:
        data = json.loads(raw)
        return {k.upper(): float(v) for k, v in data.items()}
    except Exception:
        return DEFAULT_RATES

def to_usd(amount: float | None, currency: str | None) -> tuple[str, bool]:
    if amount is None or not currency:
        return ("", False)
    c = currency.upper().strip()
    rate = fx_rates().get(c)
    if rate is None:
        return (f"{amount:g} {c}", False)
    usd = round(amount * rate, 2)
    return (f"{usd:g} USD", True)

def time_ago(dt: datetime | None) -> str:
    if not isinstance(dt, datetime):
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - dt
    s = int(delta.total_seconds())
    if s < 60:   return f"{s}s ago"
    m = s // 60
    if m < 60:   return f"{m}m ago"
    h = m // 60
    if h < 24:   return f"{h}h ago"
    d = h // 24
    return f"{d}d ago"

# ---------- Admin helpers ----------
def get_db_admin_ids() -> Set[int]:
    try:
        with get_session() as s:
            ids = [r[0] for r in s.execute(text('SELECT telegram_id FROM "user" WHERE is_admin=TRUE')).fetchall()]
        return {int(x) for x in ids if x}
    except Exception:
        return set()

def all_admin_ids() -> Set[int]:
    base = set(int(x) for x in (ADMIN_IDS or []))
    return base | get_db_admin_ids()

def is_admin_user(tid: int) -> bool:
    return tid in all_admin_ids()

# ---------- Saved jobs schema ----------
def ensure_saved_schema():
    with get_session() as s:
        s.execute(text("""
            CREATE TABLE IF NOT EXISTS saved_job (
                id BIGSERIAL PRIMARY KEY,
                user_tid BIGINT NOT NULL,
                event_id BIGINT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (user_tid, event_id)
            )
        """))
        s.commit()

# ---------- UI ----------
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
        "• Global: Freelancer.com (affiliate), PeoplePerHour, Malt, Workana, Guru, 99designs, "
        "Toptal*, Codeable*, YunoJuno*, Worksome*, twago, freelancermap\n"
        "• Greece: JobFind.gr, Skywalker.gr, Kariera.gr\n\n"
        "<b>👑 Admin:</b> <code>/users</code> <code>/grant &lt;id&gt; &lt;days&gt;</code> "
        "<code>/block &lt;id&gt;</code> <code>/unblock &lt;id&gt;</code> <code>/broadcast &lt;text&gt;</code> "
        "<code>/feedstatus</code> (alias <code>/feetstatus</code>)\n"
        "<i>Link previews are disabled for this message.</i>\n"
    )

def welcome_text(expiry: Optional[datetime]) -> str:
    extra = f"\n<b>Free trial ends:</b> {expiry.strftime('%Y-%m-%d %H:%M UTC')}" if expiry else ""
    return (
        "<b>👋 Welcome to Freelancer Alert Bot!</b>\n\n"
        "🎁 You have a <b>10-day free trial</b>.\n"
        "The bot finds matching freelance jobs from top platforms and sends instant alerts."
        f"{extra}\n\nUse <code>/help</code> for instructions.\n"
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

# ---------- Card rendering ----------
def render_card_from_event(ev: dict, matched: List[str]) -> str:
    title = ev.get("title") or "(no title)"
    platform = ev.get("platform") or "Freelancer"
    budget = ev.get("budget_amount")
    bcur = ev.get("budget_currency")
    created = ev.get("created_at")

    budget_str, _ = to_usd(budget, bcur)
    budget_line = f"<b>Budget:</b> {budget_str}\n" if budget_str else ""
    matched_line = ", ".join(matched) if matched else ""
    desc = (ev.get("description") or "").strip().replace("\n", " ")
    if len(desc) > 140: desc = desc[:139].rstrip() + "…"
    ago = time_ago(created)
    ago_line = f"\n<i>{ago}</i>" if ago else ""

    return (
        f"<b>{title}</b>\n"
        f"{budget_line}"
        f"<b>Source:</b> {platform}\n"
        f"<b>Match:</b> {matched_line}\n"
        f"✏️ {desc}{ago_line}"
    ).strip()

# ---------- Contact helpers (αμετάβλητα) ----------
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

def get_paired_admin(app: Application, user_id: int) -> Optional[int]:
    return app.bot_data.setdefault("contact_pairs", {"user_to_admin": {}, "admin_to_user": {}})["user_to_admin"].get(user_id)

def get_paired_user(app: Application, admin_id: int) -> Optional[int]:
    return app.bot_data.setdefault("contact_pairs", {"user_to_admin": {}, "admin_to_user": {}})["admin_to_user"].get(admin_id)

def unpair(app: Application, admin_id: Optional[int]=None, user_id: Optional[int]=None):
    pairs = app.bot_data.setdefault("contact_pairs", {"user_to_admin": {}, "admin_to_user": {}})
    if admin_id is not None:
        uid = pairs["admin_to_user"].pop(admin_id, None)
        if uid is not None: pairs["user_to_admin"].pop(uid, None)
    if user_id is not None:
        aid = pairs["user_to_admin"].pop(user_id, None)
        if aid is not None: pairs["admin_to_user"].pop(aid, None)

# ---------- Commands (όπως πριν, συντομευμένα) ----------
async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    role = "🧩 Admin" if is_admin_user(tid) else "👤 User"
    with get_session() as s:
        u = get_or_create_user_by_tid(s, tid)
        row = s.execute(text(
            'SELECT is_active, is_blocked, created_at, COALESCE(license_until, trial_end) '
            'FROM "user" WHERE id=:id'
        ), {"id": u.id}).fetchone()
    is_active = bool(row[0]) if row else False
    is_blocked = bool(row[1]) if row else False
    created_at = row[2] if row else None
    expires_at = row[3] if row else None
    created_str = created_at.strftime("%Y-%m-%d %H:%M") if isinstance(created_at, datetime) else "—"
    expires_str = expires_at.strftime("%Y-%m-%d %H:%M UTC") if isinstance(expires_at, datetime) else "—"
    msg = (
        "<b>Account Info</b>\n"
        f"<b>Role:</b> {role}\n"
        f"<b>Telegram ID:</b> <code>{tid}</code>\n"
        f"<b>Active:</b> {'✅' if is_active else '❌'}   "
        f"<b>Blocked:</b> {'🚫' if is_blocked else '❌'}\n"
        f"<b>Created:</b> {created_str}\n"
        f"<b>Access until:</b> {expires_str}"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        s.execute(text('UPDATE "user" SET trial_start=COALESCE(trial_start, NOW() AT TIME ZONE \'UTC\') WHERE id=:id'), {"id": u.id})
        s.execute(text(f'UPDATE "user" SET trial_end=COALESCE(trial_end, (NOW() AT TIME ZONE \'UTC\') + INTERVAL \':days days\') WHERE id=:id')
                  .bindparams(days=TRIAL_DAYS), {"id": u.id})
        expiry = s.execute(text('SELECT COALESCE(license_until, trial_end) FROM "user" WHERE id=:id'), {"id": u.id}).scalar()
        s.commit()
    await update.effective_chat.send_message(
        ("<b>👋 Welcome to Freelancer Alert Bot!</b>\n\n"
         "🎁 You have a <b>10-day free trial</b>.\n"
         "The bot finds matching freelance jobs from top platforms and sends instant alerts.\n"
         f"Free trial ends: {expiry.strftime('%Y-%m-%d %H:%M UTC') if isinstance(expiry, datetime) else '—'}\n\n"
         "Use <code>/help</code> for instructions."),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_kb(is_admin=is_admin_user(update.effective_user.id)),
    )

async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        kws = list_keywords(u.id)
        row = s.execute(text('SELECT countries, proposal_template, trial_start, trial_end, license_until, is_active, is_blocked FROM "user" WHERE id=:id'), {"id": u.id}).fetchone()
    def b(v: bool) -> str: return "✅" if v else "❌"
    k = ", ".join(kws) if kws else "(none)"
    c = row[0] if row[0] else "ALL"
    pt = "(none)" if not row[1] else "(saved)"
    ts = row[2].isoformat().replace("+00:00","Z") if row[2] else "—"
    te = row[3].isoformat().replace("+00:00","Z") if row[3] else "—"
    lic = "None" if not row[4] else row[4].isoformat().replace("+00:00","Z")
    txt = (
        "<b>🛠 Your Settings</b>\n"
        f"• <b>Keywords:</b> {k}\n"
        f"• <b>Countries:</b> {c}\n"
        f"• <b>Proposal template:</b> {pt}\n\n"
        f"<b>●</b> Start date: {ts}\n"
        f"<b>●</b> Trial ends: {te} UTC\n"
        f"<b>🔑</b> License until: {lic}\n"
        f"<b>✅ Active:</b> {b(bool(row[5]))}    <b>⛔ Blocked:</b> {b(bool(row[6]))}\n\n"
        "<b>🛰 Platforms monitored:</b> Global & GR boards.\n"
        "<i>For extension, contact the admin.</i>"
    )
    await update.message.reply_text(txt, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

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
            "Add keywords separated by commas. Example:\n<code>/addkeyword logo, lighting</code>",
            parse_mode=ParseMode.HTML); return
    kws = _parse_keywords(" ".join(context.args))
    if not kws:
        await update.message.reply_text("No valid keywords provided."); return
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
    inserted = add_keywords(u.id, kws)
    current = list_keywords(u.id)
    msg = f"✅ Added {inserted} new keyword(s)." if inserted > 0 else "ℹ️ Those keywords already exist (no changes)."
    await update.message.reply_text(msg + "\n\nCurrent keywords:\n• " + (", ".join(current) if current else "—"),
                                    parse_mode=ParseMode.HTML)

async def delkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Delete keywords. Example:\n<code>/delkeyword logo, sales</code>",
                                        parse_mode=ParseMode.HTML); return
    kws = _parse_keywords(" ".join(context.args))
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
    removed = delete_keywords(u.id, kws)
    left = list_keywords(u.id)
    await update.message.reply_text(f"🗑 Removed {removed} keyword(s).\n\nCurrent keywords:\n• " + (", ".join(left) if left else "—"),
                                    parse_mode=ParseMode.HTML)

async def clearkeywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Yes, clear all", callback_data="kw:clear:yes"),
                                InlineKeyboardButton("❌ No", callback_data="kw:clear:no")]])
    await update.message.reply_text("Clear ALL your keywords?", reply_markup=kb)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(HELP_EN + help_footer(STATS_WINDOW_HOURS),
                                             parse_mode=ParseMode.HTML, disable_web_page_preview=True)

async def selftest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # demo από job_event-like dict
    ev = {
        "id": 0,
        "platform": "Freelancer",
        "title": "Email Signature from Existing Logo",
        "description": "Please create an editable version of the email signature based on the provided logo.",
        "original_url": "https://www.freelancer.com/projects/sample",
        "affiliate_url": "https://www.freelancer.com/get/apstld?f=give&dl=https://www.freelancer.com/projects/sample",
        "budget_amount": 20.0, "budget_currency": "USD",
        "created_at": datetime.now(timezone.utc) - timedelta(minutes=1),
    }
    txt = render_card_from_event(ev, matched=["logo"])
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Proposal", url=ev["affiliate_url"]),
         InlineKeyboardButton("🔗 Original", url=ev["affiliate_url"])],
        [InlineKeyboardButton("⭐ Save", callback_data=f"job:save:{ev['id']}"),
         InlineKeyboardButton("🗑️ Delete", callback_data="job:delete")],
    ])
    await update.effective_chat.send_message(txt, parse_mode=ParseMode.HTML, reply_markup=kb)

# ---------- Admin ----------
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

async def feetstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await feedstatus_cmd(update, context)

async def grant_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_user(update.effective_user.id): return
    if len(context.args) < 2:
        await update.effective_chat.send_message("Usage: /grant <id> <days>"); return
    tid = int(context.args[0]); days = int(context.args[1])
    until = datetime.now(timezone.utc) + timedelta(days=days)
    with get_session() as s:
        s.execute(text('UPDATE "user" SET license_until=:dt WHERE telegram_id=:tid'), {"dt": until, "tid": tid}); s.commit()
    await update.effective_chat.send_message(f"✅ Granted until {until.isoformat()} for {tid}.")
    try: await context.bot.send_message(chat_id=tid, text=f"🔑 Your access is extended until {until.strftime('%Y-%m-%d %H:%M UTC')}.")
    except Exception: pass

# ---------- Callbacks ----------
async def menu_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; data = (q.data or "").strip()
    if data == "act:addkw":
        await q.message.reply_text(
            "Add keywords with:\n<code>/addkeyword logo, lighting</code>\n"
            "Remove: <code>/delkeyword logo</code> • Clear: <code>/clearkeywords</code>",
            parse_mode=ParseMode.HTML); await q.answer(); return
    if data == "act:settings":
        with get_session() as s:
            u = get_or_create_user_by_tid(s, q.from_user.id)
            kws = list_keywords(u.id)
            row = s.execute(text('SELECT countries, proposal_template, trial_start, trial_end, license_until, is_active, is_blocked FROM "user" WHERE id=:id'), {"id": u.id}).fetchone()
        def b(v: bool) -> str: return "✅" if v else "❌"
        k = ", ".join(kws) if kws else "(none)"
        c = row[0] if row[0] else "ALL"
        pt = "(none)" if not row[1] else "(saved)"
        ts = row[2].isoformat().replace("+00:00","Z") if row[2] else "—"
        te = row[3].isoformat().replace("+00:00","Z") if row[3] else "—"
        lic = "None" if not row[4] else row[4].isoformat().replace("+00:00","Z")
        txt = (
            "<b>🛠 Your Settings</b>\n"
            f"• <b>Keywords:</b> {k}\n"
            f"• <b>Countries:</b> {c}\n"
            f"• <b>Proposal template:</b> {pt}\n\n"
            f"<b>●</b> Start date: {ts}\n"
            f"<b>●</b> Trial ends: {te} UTC\n"
            f"<b>🔑</b> License until: {lic}\n"
            f"<b>✅ Active:</b> {b(bool(row[5]))}    <b>⛔ Blocked:</b> {b(bool(row[6]))}\n\n"
            "<b>🛰 Platforms monitored:</b> Global & GR boards.\n"
            "<i>For extension, contact the admin.</i>"
        )
        await q.message.reply_text(txt, parse_mode=ParseMode.HTML, disable_web_page_preview=True); await q.answer(); return
    if data == "act:help":
        await q.message.reply_text(HELP_EN + help_footer(STATS_WINDOW_HOURS),
                                   parse_mode=ParseMode.HTML, disable_web_page_preview=True); await q.answer(); return
    if data == "act:saved":
        ensure_saved_schema()
        # Πάρε τις αποθηκευμένες του χρήστη με join στο job_event
        with get_session() as s:
            rows = s.execute(text("""
                SELECT je.id, je.platform, je.title, je.description, je.original_url, je.affiliate_url,
                       je.budget_amount, je.budget_currency, je.created_at
                FROM saved_job sj
                JOIN job_event je ON je.id = sj.event_id
                WHERE sj.user_tid = :tid
                ORDER BY sj.created_at DESC
                LIMIT 10
            """), {"tid": q.from_user.id}).fetchall()
        if not rows:
            await q.message.reply_text("No saved jobs yet."); await q.answer(); return
        for r in rows:
            ev = {
                "id": r[0], "platform": r[1], "title": r[2], "description": r[3] or "",
                "original_url": r[4], "affiliate_url": r[5],
                "budget_amount": r[6], "budget_currency": r[7], "created_at": r[8],
            }
            txt = render_card_from_event(ev, matched=[])
            url = ev["affiliate_url"] or ev["original_url"]
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📄 Proposal", url=url),
                 InlineKeyboardButton("🔗 Original", url=url)],
                [InlineKeyboardButton("🗑️ Delete", callback_data=f"saved:delete:{ev['id']}")]
            ])
            await q.message.chat.send_message(txt, parse_mode=ParseMode.HTML, reply_markup=kb, disable_web_page_preview=True)
        await q.answer(); return
    if data.startswith("saved:delete:"):
        try:
            _, _, ev_id_str = data.split(":")
            ev_id = int(ev_id_str)
        except Exception:
            return await q.answer()
        with get_session() as s:
            s.execute(text("DELETE FROM saved_job WHERE user_tid=:tid AND event_id=:eid"),
                      {"tid": q.from_user.id, "eid": ev_id}); s.commit()
        try: await q.message.delete()
        except Exception: pass
        return await q.answer("Removed from Saved")
    if data == "act:admin":
        if not is_admin_user(q.from_user.id):
            await q.answer("Not allowed", show_alert=True); return
        await q.message.reply_text(
            "<b>Admin panel</b>\n"
            "<code>/users</code> • <code>/grant &lt;id&gt; &lt;days&gt;</code>\n"
            "<code>/block &lt;id&gt;</code> • <code>/unblock &lt;id&gt;</code>\n"
            "<code>/broadcast &lt;text&gt;</code> • <code>/feedstatus</code>",
            parse_mode=ParseMode.HTML
        ); await q.answer(); return
    await q.answer()

async def kw_clear_confirm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q.data.startswith("kw:clear:"): return await q.answer()
    if q.data.endswith(":no"):
        await q.message.reply_text("Cancelled."); return await q.answer()
    with get_session() as s:
        u = get_or_create_user_by_tid(s, q.from_user.id)
    n = clear_keywords(u.id)
    await q.message.reply_text(f"🗑 Cleared {n} keyword(s)."); await q.answer()

async def admin_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin_user(q.from_user.id): return await q.answer("Not allowed", show_alert=True)
    parts = (q.data or "").split(":")
    if len(parts) < 3 or parts[0] != "adm": return await q.answer()
    action, target = parts[1], int(parts[2])

    if action == "reply":
        pair_admin_user(context.application, q.from_user.id, target)
        await q.message.reply_text(f"Replying to <code>{target}</code>. Type your messages.", parse_mode=ParseMode.HTML)
        return await q.answer()
    if action == "decline":
        unpair(context.application, user_id=target); return await q.answer("Declined")
    if action == "grant":
        days = int(parts[3]) if len(parts) >= 4 else 30
        until = datetime.now(timezone.utc) + timedelta(days=days)
        with get_session() as s:
            s.execute(text('UPDATE "user" SET license_until=:dt WHERE telegram_id=:tid'), {"dt": until, "tid": target}); s.commit()
        try: await context.bot.send_message(chat_id=target, text=f"🔑 Your access is extended until {until.strftime('%Y-%m-%d %H:%M UTC')}.")
        except Exception: pass
        return await q.answer(f"Granted +{days}d")
    await q.answer()

async def job_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save/Delete on job cards — Save by event_id, then delete message immediately."""
    q = update.callback_query
    data = q.data or ""

    # job:save:<event_id>
    if data.startswith("job:save:"):
        try:
            _, _, id_str = data.split(":")
            ev_id = int(id_str)
        except Exception:
            return await q.answer("Save error")
        ensure_saved_schema()
        with get_session() as s:
            s.execute(text("""
                INSERT INTO saved_job (user_tid, event_id)
                VALUES (:tid, :eid)
                ON CONFLICT (user_tid, event_id) DO NOTHING
            """), {"tid": q.from_user.id, "eid": ev_id})
            s.commit()
        try: await q.message.delete()
        except Exception: pass
        return await q.answer("Saved ⭐")

    if data == "job:delete":
        try: await q.message.delete()
        except Exception: pass
        return await q.answer("Deleted 🗑")

    await q.answer()

# ---------- Router (συνεχές chat admin<->user, αμετάβλητο) ----------
def get_paired_admin(app: Application, user_id: int) -> Optional[int]:
    return app.bot_data.setdefault("contact_pairs", {"user_to_admin": {}, "admin_to_user": {}})["user_to_admin"].get(user_id)
def get_paired_user(app: Application, admin_id: int) -> Optional[int]:
    return app.bot_data.setdefault("contact_pairs", {"user_to_admin": {}, "admin_to_user": {}})["admin_to_user"].get(admin_id)
def pair_admin_user(app: Application, admin_id: int, user_id: int) -> None:
    pairs = app.bot_data.setdefault("contact_pairs", {"user_to_admin": {}, "admin_to_user": {}})
    pairs["user_to_admin"][user_id] = admin_id
    pairs["admin_to_user"][admin_id] = user_id

async def incoming_message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text or update.message.text.startswith("/"):
        return
    text_msg = update.message.text.strip()
    sender_id = update.effective_user.id
    app = context.application

    if is_admin_user(sender_id):
        paired_user = get_paired_user(app, sender_id)
        if paired_user:
            try: await context.bot.send_message(chat_id=paired_user, text=text_msg)
            except Exception: pass
            return

    paired_admin = get_paired_admin(app, sender_id)
    if paired_admin:
        try:
            await context.bot.send_message(chat_id=paired_admin,
                                           text=f"✉️ From {sender_id}:\n\n{text_msg}",
                                           reply_markup=InlineKeyboardMarkup([
                                               [InlineKeyboardButton("💬 Reply", callback_data=f"adm:reply:{sender_id}"),
                                                InlineKeyboardButton("❌ Decline", callback_data=f"adm:decline:{sender_id}")]
                                           ]))
        except Exception: pass
        return

    for aid in all_admin_ids():
        try:
            await context.bot.send_message(
                chat_id=aid,
                text=f"✉️ <b>New message from user</b>\nID: <code>{sender_id}</code>\n\n{text_msg}",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💬 Reply", callback_data=f"adm:reply:{sender_id}"),
                     InlineKeyboardButton("❌ Decline", callback_data=f"adm:decline:{sender_id}")]
                ]),
            )
        except Exception: pass
    await update.message.reply_text("Thanks! Your message was forwarded to the admin 👌")

# ---------- Expiry reminders (όπως πριν) ----------
async def notify_expiring_job(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(timezone.utc); soon = now + timedelta(hours=24)
    with get_session() as s:
        rows = s.execute(text('SELECT telegram_id, COALESCE(license_until, trial_end) FROM "user" WHERE is_active=TRUE AND is_blocked=FALSE')).fetchall()
    for tid, expiry in rows:
        if not expiry: continue
        if getattr(expiry, "tzinfo", None) is None: expiry = expiry.replace(tzinfo=timezone.utc)
        if now < expiry <= soon:
            try:
                hours_left = int((expiry - now).total_seconds() // 3600)
                await context.bot.send_message(chat_id=tid, text=f"⏰ Reminder: your access expires in about {hours_left} hours (on {expiry.strftime('%Y-%m-%d %H:%M UTC')}).")
            except Exception: pass

async def _background_expiry_loop(app: Application):
    await asyncio.sleep(5)
    while True:
        try:
            await notify_expiring_job(type("Ctx", (), {"bot": app.bot})())
        except Exception as e:
            log.exception("expiry loop error: %s", e)
        await asyncio.sleep(3600)

# ---------- Build app ----------
def build_application() -> Application:
    ensure_schema()
    ensure_feed_events_schema()
    ensure_keyword_unique()
    ensure_saved_schema()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # public
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("whoami", whoami_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))
    app.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app.add_handler(CommandHandler("delkeyword", delkeyword_cmd))
    app.add_handler(CommandHandler("clearkeywords", clearkeywords_cmd))
    app.add_handler(CommandHandler("selftest", selftest_cmd))

    # admin
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CommandHandler("grant", grant_cmd))
    app.add_handler(CommandHandler("feedstatus", feedstatus_cmd))
    app.add_handler(CommandHandler("feetstatus", feedstatus_cmd))

    # callbacks
    app.add_handler(CallbackQueryHandler(menu_action_cb, pattern=r"^act:(addkw|settings|help|saved|contact|admin)$"))
    app.add_handler(CallbackQueryHandler(kw_clear_confirm_cb, pattern=r"^kw:clear:(yes|no)$"))
    app.add_handler(CallbackQueryHandler(admin_action_cb, pattern=r"^adm:(reply|decline|grant):"))
    app.add_handler(CallbackQueryHandler(job_action_cb, pattern=r"^job:(save|delete)(:\d+)?$"))

    # text router
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, incoming_message_router))

    # scheduler
    try:
        if JobQueue is not None:
            jq = app.job_queue or JobQueue()
            if app.job_queue is None: jq.set_application(app)
            jq.run_repeating(notify_expiring_job, interval=3600, first=60)  # type: ignore[arg-type]
            log.info("Scheduler: JobQueue")
        else:
            raise RuntimeError("no jobqueue")
    except Exception:
        app.bot_data["expiry_task"] = asyncio.get_event_loop().create_task(_background_expiry_loop(app))
        log.info("Scheduler: fallback loop (started immediately)")
    return app
