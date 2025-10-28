import logging
from datetime import datetime, timezone
from sqlalchemy import text

from db import get_session

log = logging.getLogger("utils")

# =====================================================
# USER MANAGEMENT UTILITIES
# =====================================================

def get_or_create_user_by_tid(s, telegram_id):
    """
    Ensures that a user with the given Telegram ID exists in the database.
    Returns the user row (SQLAlchemy row or dict-like).
    """
    if not telegram_id:
        log.warning("get_or_create_user_by_tid called with empty telegram_id")
        return None

    user = s.execute(
        text("SELECT * FROM users WHERE telegram_id=:tid"),
        {"tid": telegram_id}
    ).fetchone()

    if user:
        return user

    log.info("Creating new user with telegram_id=%s", telegram_id)
    s.execute(
        text("""
            INSERT INTO users (telegram_id, is_active, created_at)
            VALUES (:tid, TRUE, NOW() AT TIME ZONE 'UTC')
        """),
        {"tid": telegram_id}
    )
    s.commit()

    return s.execute(
        text("SELECT * FROM users WHERE telegram_id=:tid"),
        {"tid": telegram_id}
    ).fetchone()


def is_admin_user(telegram_id):
    """
    Checks whether the user is an admin (based on users table).
    """
    if not telegram_id:
        return False
    try:
        with get_session() as s:
            row = s.execute(
                text("SELECT is_admin FROM users WHERE telegram_id=:tid"),
                {"tid": telegram_id}
            ).fetchone()
            if row and (row[0] is True or str(row[0]).lower() == "t"):
                return True
    except Exception as e:
        log.warning("is_admin_user check failed for %s: %s", telegram_id, e)
    return False


# =====================================================
# TEXT GENERATION HELPERS
# =====================================================

def welcome_text(expiry_date: datetime | None = None):
    """
    Returns the formatted welcome message for the /start command.
    """
    base = (
        "👋 <b>Welcome to Freelancer Alert Bot!</b>\n\n"
        "You’ll receive alerts from Freelancer, PeoplePerHour, and Greek job boards "
        "based on your saved keywords.\n\n"
    )
    if expiry_date:
        base += f"⏳ Trial access active until <b>{expiry_date.strftime('%d %b %Y')}</b>.\n"
    else:
        base += "🆓 You are currently on a trial plan.\n"

    base += "\nUse the menu below to explore available actions 👇"
    return base


def help_footer(hours: int = 24):
    """
    Returns help text footer for /help or inline messages.
    """
    return (
        f"\n\nℹ️ Stats are refreshed every {hours}h.\n"
        "To adjust your keywords or view saved jobs, use the ⚙️ Settings menu."
    )


# =====================================================
# FORMATTERS
# =====================================================

def format_currency(amount, currency):
    """
    Format numeric amount + currency code safely.
    """
    if amount is None:
        return "N/A"
    try:
        return f"{float(amount):,.2f} {currency or ''}".strip()
    except Exception:
        return f"{amount} {currency or ''}".strip()


def format_time_ago(dt: datetime):
    """
    Returns human-readable 'time ago' text (e.g., '2 hours ago').
    """
    if not dt:
        return "N/A"
    if not isinstance(dt, datetime):
        return str(dt)

    now = datetime.now(timezone.utc)
    delta = now - dt
    seconds = int(delta.total_seconds())

    if seconds < 60:
        return f"{seconds} sec ago"
    elif seconds < 3600:
        return f"{seconds // 60} min ago"
    elif seconds < 86400:
        return f"{seconds // 3600} hours ago"
    else:
        return f"{seconds // 86400} days ago"


# =====================================================
# GENERIC LOG WRAPPER
# =====================================================

def safe_log(title, data):
    """
    Simple logger to debug runtime variables without breaking code.
    """
    try:
        log.info("%s: %s", title, data)
    except Exception:
        pass
