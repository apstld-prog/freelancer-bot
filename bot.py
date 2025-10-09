# bot.py — full replacement (English code, Greek UX)
import os
import logging
from datetime import datetime, timedelta
from typing import List, Iterable, Tuple

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

# --- Project-local modules (already in your codebase) ---
from db import (
    ensure_schema,
    get_session,
    get_or_create_user_by_tid,
    list_user_keywords,
    add_user_keywords,          # existing helper (unknown signature)
    User,
    # Optional helpers (may or may not exist)
    # remove_user_keyword,
    # set_user_keywords,
)
from config import ADMIN_IDS, TRIAL_DAYS, STATS_WINDOW_HOURS
from db_events import get_platform_stats

log = logging.getLogger("bot")

TELEGRAM_BOT_TOKEN = (
    os.getenv("TELEGRAM_BOT_TOKEN")
    or os.getenv("BOT_TOKEN")
    or os.getenv("TELEGRAM_TOKEN")
)
if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN env var is required")

# ======================================================
# UI (Greek messages; code identifiers in English)
# ======================================================
def main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    row1 = [
        InlineKeyboardButton("➕ Προσθήκη Λέξεων", callback_data="act:addkw"),
        InlineKeyboardButton("⚙️ Ρυθμίσεις", callback_data="act:settings"),
    ]
    row2 = [
        InlineKeyboardButton("🆘 Βοήθεια", callback_data="act:help"),
        InlineKeyboardButton("💾 Αποθηκευμένα", callback_data="act:saved"),
    ]
    row3 = [InlineKeyboardButton("📨 Επικοινωνία", callback_data="act:contact")]
    kb = [row1, row2, row3]
    if is_admin:
        kb.append([InlineKeyboardButton("🔥 Admin", callback_data="act:admin")])
    return InlineKeyboardMarkup(kb)


def welcome_full(trial_days: int) -> str:
    return (
        "<b>👋 Καλωσήρθες στο Freelancer Alert Bot!</b>\n\n"
        f"🎁 Έχεις <b>{trial_days} ημέρες δωρεάν δοκιμή</b>.\n"
        "Το bot βρίσκει αυτόματα αγγελίες που ταιριάζουν με τα keywords σου και στέλνει άμεσα ειδοποιήσεις.\n\n"
        "Χρησιμοποίησε <code>/help</code> για οδηγίες.\n"
    )


def features_block() -> str:
    return (
        "<b>✨ Features</b>\n"
        "• Real-time job alerts (Freelancer API)\n"
        "• Affiliate-wrapped <b>Πρόταση</b> & <b>Αυθεντικό</b> links\n"
        "• Εμφάνιση budget + μετατροπή σε USD\n"
        "• ⭐ Κράτησε / 🗑 Διέγραψε\n"
        "• 10-day free trial (επέκταση από admin)\n"
        "• Multi-keyword αναζήτηση\n"
        "• Πλατφόρμες ανά χώρα (συμπ. GR boards)\n"
    )


HELP_EL = (
    "<b>🧭 Help / Πως δουλεύει</b>\n\n"
    "<b>1)</b> Πρόσθεσε λέξεις-κλειδιά με <code>/addkeyword</code> π.χ. <i>python, telegram</i> (χωρισμένες με κόμμα, Ελληνικά ή Αγγλικά).\n"
    "<b>2)</b> Ρύθμισε χώρες με <code>/setcountry</code> π.χ. <i>US,UK</i> (ή <i>ALL</i>).\n"
    "<b>3)</b> Αποθήκευσε πρότυπο πρότασης με <code>/setproposal &lt;κείμενο&gt;</code> — "
    "placeholders: <code>{jobtitle}</code>, <code>{experience}</code>, <code>{stack}</code>, "
    "<code>{availability}</code>, <code>{step1}</code>, <code>{step2}</code>, <code>{step3}</code>, "
    "<code>{budgettime}</code>, <code>{portfolio}</code>, <code>{name}</code>.\n"
    "<b>4)</b> Όταν έρχεται αγγελία: κράτησέ την, διέγραψέ την, άνοιξε <b>Πρόταση</b> ή <b>Αυθεντικό</b> link.\n\n"
    "<b>Χρησιμοποίησε</b> <code>/mysettings</code> για να δεις τα φίλτρα σου. Δοκίμασε <code>/selftest</code> για δείγμα.\n"
    "<b>/platforms</b> CC για πλατφόρμες ανά χώρα (π.χ. <code>/platforms GR</code>).\n"
)


def help_footer(hours: int) -> str:
    return (
        "\n<b>🛰 Πλατφόρμες:</b>\n"
        "• Global: <a href=\"https://www.freelancer.com\">Freelancer.com</a> (affiliate links), "
        "PeoplePerHour, Malt, Workana, Guru, 99designs, Toptal*, Codeable*, YunoJuno*, Worksome*, twago, freelancermap\n"
        "  <i>(* referral/curated)</i>\n"
        "• Greece: <a href=\"https://www.jobfind.gr\">JobFind.gr</a>, "
        "<a href=\"https://www.skywalker.gr\">Skywalker.gr</a>, <a href=\"https://www.kariera.gr\">Kariera.gr</a>\n\n"
        "<b>👑 Admin:</b>\n"
        "<code>/users</code>, <code>/grant &lt;id&gt; &lt;days&gt;</code>, "
        "<code>/block &lt;id&gt;</code>/<code>/unblock &lt;id&gt;</code>, "
        "<code>/broadcast &lt;text&gt;</code>, <code>/feedstatus</code>\n"
        "<i>web preview απενεργοποιημένο για καθαρό help.</i>\n"
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
        "<b>🛰 Πλατφόρμες:</b>\n"
        "• Global: <a href=\"https://www.freelancer.com\">Freelancer.com</a> (affiliate links), PeoplePerHour, "
        "Malt, Workana, Guru, 99designs, Toptal*, Codeable*, YunoJuno*, Worksome*, twago, freelancermap\n"
        "  <i>(* referral/curated)</i>\n"
        "• Greece: <a href=\"https://www.jobfind.gr\">JobFind.gr</a>, "
        "<a href=\"https://www.skywalker.gr\">Skywalker.gr</a>, <a href=\"https://www.kariera.gr\">Kariera.gr</a>\n\n"
        "<i>Για επέκταση, επικοινώνησε με admin.</i>"
    )

# ======================================================
# Keyword helpers (robust to unknown helper signatures)
# ======================================================
def parse_keywords_input(raw: str) -> List[str]:
    # Accept both comma-separated and space-separated
    parts = [p.strip() for chunk in raw.split(",") for p in chunk.split() if p.strip()]
    # De-duplicate case-insensitively
    seen = set(); clean = []
    for p in parts:
        k = p.lower()
        if k not in seen:
            seen.add(k)
            clean.append(p)
    return clean

def add_keywords_safe(db_session, user_id: int, keywords: List[str]) -> int:
    """
    Tries to call add_user_keywords with either List[str] or comma string.
    Returns number of inserted keywords if helper returns it, else best-effort count.
    """
    if not keywords:
        return 0
    inserted = 0
    try:
        # Try list signature
        res = add_user_keywords(db_session, user_id, keywords)  # type: ignore[arg-type]
        inserted = int(res) if res is not None else 0
        if inserted == 0:
            # maybe helper doesn't return count; recompute
            current = list_user_keywords(db_session, user_id) or []
            new_set = set([*current, *keywords])
            inserted = max(0, len(new_set) - len(current))
    except TypeError:
        # Fallback: pass comma-separated string
        try:
            text = ", ".join(keywords)
            res = add_user_keywords(db_session, user_id, text)  # type: ignore[misc]
            inserted = int(res) if res is not None else 0
            if inserted == 0:
                current = list_user_keywords(db_session, user_id) or []
                new_set = set([*current, *keywords])
                inserted = max(0, len(new_set) - len(current))
        except Exception:
            inserted = 0
    return inserted

def remove_keyword_safe(db_session, user_id: int, keyword: str) -> bool:
    """
    Attempts to remove a keyword using a likely helper if it exists in db.py.
    If no helper is present, returns False (and we instruct user to use /setkeywords in the future).
    """
    try:
        # If your db.py has remove_user_keyword(session, user_id, keyword)
        from db import remove_user_keyword  # type: ignore
        before = list_user_keywords(db_session, user_id) or []
        if keyword in before:
            remove_user_keyword(db_session, user_id, keyword)  # type: ignore
            after = list_user_keywords(db_session, user_id) or []
            return keyword not in after
        return False
    except Exception:
        return False

# ======================================================
# Public commands
# ======================================================
async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Το ID σου είναι: <code>{update.effective_user.id}</code>",
        parse_mode=ParseMode.HTML,
    )

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as db:
        u = get_or_create_user_by_tid(db, update.effective_user.id)
        _ = list_user_keywords(db, u.id)
    is_admin = update.effective_user.id in ADMIN_IDS
    await update.effective_chat.send_message(
        welcome_full(trial_days=TRIAL_DAYS),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_kb(is_admin=is_admin),
    )
    await update.effective_chat.send_message(features_block(), parse_mode=ParseMode.HTML)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(
        HELP_EL + help_footer(STATS_WINDOW_HOURS),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )

async def addkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Πρόσθεσε λέξεις-κλειδιά χωρισμένες με κόμμα. Παράδειγμα:\n"
            "<code>/addkeyword logo, lighting</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    raw = " ".join(context.args)
    keywords = parse_keywords_input(raw)
    if not keywords:
        await update.message.reply_text("Δεν δόθηκαν έγκυρες λέξεις-κλειδιά.", parse_mode=ParseMode.HTML)
        return
    with get_session() as db:
        u = get_or_create_user_by_tid(db, update.effective_user.id)
        inserted = add_keywords_safe(db, u.id, keywords)
        current = list_user_keywords(db, u.id) or []
    msg = f"✅ Προστέθηκαν {inserted} νέες λέξεις.\n\nΤρέχουσες λέξεις-κλειδιά:\n• " + (", ".join(current) if current else "—")
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

async def keywords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as db:
        u = get_or_create_user_by_tid(db, update.effective_user.id)
        current = list_user_keywords(db, u.id) or []
    text = (
        "<b>Λέξεις-κλειδιά</b>\n"
        "• " + (", ".join(current) if current else "—") + "\n\n"
        "Πρόσθεσε με <code>/addkeyword logo, lighting</code>\n"
        "Αφαίρεσε με <code>/delkeyword logo</code>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def delkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Χρήση: <code>/delkeyword &lt;λέξη&gt;</code>", parse_mode=ParseMode.HTML)
        return
    kw = " ".join(context.args).strip()
    with get_session() as db:
        u = get_or_create_user_by_tid(db, update.effective_user.id)
        ok = remove_keyword_safe(db, u.id, kw)
        current = list_user_keywords(db, u.id) or []
    if ok:
        await update.message.reply_text(
            f"🗑 Διαγράφηκε η λέξη <b>{kw}</b>.\nΤρέχουσες: " + (", ".join(current) if current else "—"),
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(
            "Δεν μπόρεσα να τη διαγράψω αυτόματα.\n"
            "Προς το παρόν μπορείς να διαχειριστείς τη λίστα προσθέτοντας νέες λέξεις με /addkeyword.",
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
        "✏️ Παρακαλώ κάνε ένα editable αντίγραφο της υπογραφής email με βάση το υπάρχον logo.\n"
    )
    proposal_url = "https://www.freelancer.com/get/apstld?f=give&dl=https://www.freelancer.com/projects/sample"
    original_url = proposal_url
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📄 Πρόταση", url=proposal_url), InlineKeyboardButton("🔗 Αυθεντικό", url=original_url)],
            [InlineKeyboardButton("⭐ Αποθήκευση", callback_data="job:save"), InlineKeyboardButton("🗑️ Διαγραφή", callback_data="job:delete")],
        ]
    )
    await update.effective_chat.send_message(job_text, parse_mode=ParseMode.HTML, reply_markup=kb)

# ======================================================
# Admin
# ======================================================
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
        await update.effective_chat.send_message("Χρήση: /grant <telegram_id> <days>")
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
    await update.effective_chat.send_message(f"✅ Δόθηκε άδεια έως {until.isoformat()} για {tg_id}.")

async def block_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.effective_chat.send_message("Χρήση: /block <telegram_id>")
        return
    tg_id = int(context.args[0])
    with get_session() as db:
        u = db.query(User).filter(User.telegram_id == tg_id).first()
        if not u:
            await update.effective_chat.send_message("User not found.")
            return
        setattr(u, "is_blocked", True)
        db.commit()
    await update.effective_chat.send_message(f"⛔ Ο χρήστης {tg_id} μπλοκαρίστηκε.")

async def unblock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.effective_chat.send_message("Χρήση: /unblock <telegram_id>")
        return
    tg_id = int(context.args[0])
    with get_session() as db:
        u = db.query(User).filter(User.telegram_id == tg_id).first()
        if not u:
            await update.effective_chat.send_message("User not found.")
            return
        setattr(u, "is_blocked", False)
        db.commit()
    await update.effective_chat.send_message(f"✅ Ο χρήστης {tg_id} ξεμπλοκαρίστηκε.")

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.effective_chat.send_message("Χρήση: /broadcast <κείμενο>")
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
    await update.effective_chat.send_message(f"📣 Εστάλη σε {sent} χρήστες.")

async def feedstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return
    stats = get_platform_stats(STATS_WINDOW_HOURS)
    if not stats:
        await update.effective_chat.send_message(f"Δεν υπάρχουν γεγονότα τις τελευταίες {STATS_WINDOW_HOURS} ώρες.")
        return
    lines = [f"📊 Κατάσταση feeds (τελευταίες {STATS_WINDOW_HOURS}h):"]
    for src, cnt in stats.items():
        lines.append(f"• {src}: {cnt}")
    await update.effective_chat.send_message("\n".join(lines))

# ======================================================
# Menu callbacks
# ======================================================
async def menu_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = (q.data or "").strip()

    if data == "act:addkw":
        await q.message.reply_text(
            "Πρόσθεσε λέξεις-κλειδιά (χωρισμένες με κόμμα). Παράδειγμα:\n"
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
        await q.message.reply_text(HELP_EL + help_footer(STATS_WINDOW_HOURS),
                                   parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        await q.answer(); return

    if data == "act:saved":
        await q.message.reply_text("💾 Αποθηκευμένα (σύντομα).")
        await q.answer(); return

    if data == "act:contact":
        await q.message.reply_text("📨 Στείλε μήνυμα εδώ για επικοινωνία με admin.")
        await q.answer(); return

    if data == "act:admin":
        if update.effective_user.id not in ADMIN_IDS:
            await q.answer("Δεν επιτρέπεται", show_alert=True); return
        await q.message.reply_text(
            "<b>Admin panel</b>\n"
            "/users — λίστα χρηστών\n"
            "/grant &lt;id&gt; &lt;days&gt; — άδεια\n"
            "/block &lt;id&gt; / /unblock &lt;id&gt;\n"
            "/broadcast &lt;text&gt;\n"
            "/feedstatus — στατιστικά ανά πλατφόρμα",
            parse_mode=ParseMode.HTML,
        )
        await q.answer(); return

    await q.answer()

# ======================================================
# Application factory
# ======================================================
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
