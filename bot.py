import os
import logging
from datetime import datetime, timezone
from typing import List, Tuple

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# === Logging ===
log = logging.getLogger("bot")
logging.basicConfig(level=logging.INFO)


# === DB layer (expects db.py with these names) ===
# The code is tolerant: if your existing db.py exposes different shapes, we won't crash the bot flow.
try:
    from db import (
        SessionLocal,              # -> sessionmaker() or similar
        ensure_schema,             # -> creates/adjusts tables/columns if needed
        User,                      # -> SQLAlchemy model
        Keyword,                   # -> SQLAlchemy model with fields: id, user_id, value, created_at, updated_at
        get_or_create_user_by_tid, # -> (db, telegram_id) -> User
        get_keywords_for_user,     # -> (db, user_id) -> List[Keyword]
        add_keywords_for_user,     # -> (db, user_id, values: List[str]) -> Tuple[int, int]
    )
except Exception as e:
    log.warning("db.py import failed or has different API: %s", e)

    # Fallback shims to keep the bot responsive even if db module API differs.
    SessionLocal = None
    def ensure_schema():
        log.info("ensure_schema(): skipped (no db.py)")

    class _DummyUser:
        id = 0
        telegram_id = 0
        is_admin = False
        is_active = True
        is_blocked = False
        created_at = datetime.now(timezone.utc)
        updated_at = datetime.now(timezone.utc)

    User = _DummyUser

    class _DummyKeyword:
        id = 0
        user_id = 0
        value = ""
        created_at = datetime.now(timezone.utc)
        updated_at = datetime.now(timezone.utc)

    Keyword = _DummyKeyword

    def get_or_create_user_by_tid(db, telegram_id: int):
        u = _DummyUser()
        u.id = 1
        u.telegram_id = telegram_id
        return u

    def get_keywords_for_user(db, user_id: int):
        return []

    def add_keywords_for_user(db, user_id: int, values: List[str]) -> Tuple[int, int]:
        # (inserted, skipped)
        return (0, len(values))


# === Utilities ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
if not TELEGRAM_TOKEN:
    log.warning("TELEGRAM_TOKEN is empty — server.py must not build Application (will crash there).")

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def as_list_from_csv(s: str) -> List[str]:
    parts = [p.strip() for p in (s or "").replace(";", ",").split(",")]
    return [p for p in parts if p]


# === Simple cards (text only – keep your own styling elsewhere) ===
def welcome_text() -> str:
    return (
        "👋 Καλωσήρθες!\n"
        "• Πρόσθεσε λέξεις-κλειδιά: /addkeyword logo, lighting\n"
        "• Δες τις ρυθμίσεις σου: /mysettings\n"
        "• Βοήθεια: /help\n"
    )

def help_text() -> str:
    return (
        "<b>Βοήθεια</b>\n"
        "• /start — αρχική οθόνη\n"
        "• /help — αυτή η βοήθεια\n"
        "• /addkeyword <λέξεις χωρισμένες με κόμμα> — προσθέτει λέξεις-κλειδιά\n"
        "• /mysettings — προβάλλει τις τρέχουσες λέξεις-κλειδιά\n"
        "\n"
        "Παράδειγμα: <code>/addkeyword logo, lighting</code>\n"
    )

def settings_card(user: User, kws: List[Keyword]) -> str:
    if not kws:
        kws_html = "<i>Δεν έχεις δηλώσει λέξεις-κλειδιά ακόμα.</i>"
    else:
        kws_html = "• " + "\n• ".join(f"<code>{k.value}</code>" for k in kws)

    return (
        "<b>Τα προσωπικά σου settings</b>\n\n"
        "<b>Λέξεις-κλειδιά</b>:\n"
        f"{kws_html}\n"
    )

def main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("⚙️ Settings", callback_data="act:settings")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="act:help")],
    ]
    if is_admin:
        buttons.append([InlineKeyboardButton("🛠 Admin", callback_data="act:admin")])
    return InlineKeyboardMarkup(buttons)


# === Handlers ===
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Robust /start: answer whether update carries message or callback.
    """
    text = welcome_text()
    kb = main_menu_kb(is_admin=False)

    if update.message:
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=kb,
        )
        return

    if update.callback_query:
        q = update.callback_query
        await q.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=kb,
        )
        await q.answer()
        return

    # Fallback (rare)
    chat_id = None
    try:
        chat_id = update.effective_chat.id
    except Exception:
        pass
    if chat_id:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=kb,
        )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = help_text()
    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    elif update.callback_query:
        q = update.callback_query
        await q.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        await q.answer()


async def addkeyword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /addkeyword logo, lighting
    Stores keywords per user. Keeps layout unchanged elsewhere.
    """
    # resolve user & text
    if update.message:
        chat_id = update.message.chat_id
        text = (update.message.text or "").strip()
    elif update.callback_query:
        chat_id = update.callback_query.message.chat_id
        text = (update.callback_query.message.text or "").strip()
    else:
        # nothing to do
        return

    # extract after command word
    parts = (text.split(" ", 1) + [""])[:2]
    payload = parts[1].strip()

    if not payload:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Δώσε λέξεις-κλειδιά χωρισμένες με κόμμα. Παράδειγμα:\n<code>/addkeyword logo, lighting</code>",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        return

    values = as_list_from_csv(payload)
    if not values:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Δεν βρέθηκαν λέξεις-κλειδιά στο μήνυμα.",
            parse_mode=ParseMode.HTML,
        )
        return

    # DB ops
    try:
        db = SessionLocal()
        user = get_or_create_user_by_tid(db, chat_id)
        inserted, skipped = add_keywords_for_user(db, user.id, values)
        db.commit()
        msg = f"Προστέθηκαν: <b>{inserted}</b>, αγνοήθηκαν (διπλότυπα): <b>{skipped}</b>."
    except Exception as e:
        log.exception("addkeyword failed: %s", e)
        if 'db' in locals():
            db.rollback()
        msg = "Σφάλμα κατά την αποθήκευση των λέξεων-κλειδιών."
    finally:
        if 'db' in locals():
            db.close()

    await context.bot.send_message(
        chat_id=chat_id,
        text=msg,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def mysettings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # resolve chat id
    if update.message:
        chat_id = update.message.chat_id
    elif update.callback_query:
        chat_id = update.callback_query.message.chat_id
    else:
        return

    # DB read
    try:
        db = SessionLocal()
        user = get_or_create_user_by_tid(db, chat_id)
        kws = get_keywords_for_user(db, user.id)
    except Exception as e:
        log.exception("mysettings failed: %s", e)
        if 'db' in locals():
            db.rollback()
        kws = []
        user = User()
        user.is_admin = False
    finally:
        if 'db' in locals():
            db.close()

    text = settings_card(user, kws)
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=main_menu_kb(is_admin=getattr(user, "is_admin", False) is True),
    )


async def menu_action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inline keyboard actions for main menu."""
    q = update.callback_query
    data = (q.data or "").strip()

    if data == "act:settings":
        await mysettings_cmd(update, context)
        await q.answer()
        return

    if data == "act:help":
        await help_cmd(update, context)
        await q.answer()
        return

    if data == "act:admin":
        # Keep minimal; do not alter your existing admin UI here.
        await q.message.reply_text("Admin panel (placeholder).")
        await q.answer()
        return

    await q.answer("OK")


# === Build application ===
def build_application() -> Application:
    """Build and return a PTB Application."""
    ensure_schema()

    token = TELEGRAM_TOKEN
    if not token:
        # Server will raise earlier, but keep a clear log here too
        raise RuntimeError("TELEGRAM_TOKEN is not set in environment.")

    app = ApplicationBuilder().token(token).build()

    # Core commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("addkeyword", addkeyword_cmd))
    app.add_handler(CommandHandler("mysettings", mysettings_cmd))

    # Menu callback
    app.add_handler(CallbackQueryHandler(menu_action_cb, pattern=r"^act:(settings|help|admin)$"))

    log.info("Handlers ready: /start /help /addkeyword /mysettings + menu callbacks")
    return app
