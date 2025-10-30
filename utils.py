import logging
import httpx
from datetime import datetime, timezone
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from currency_usd import usd_line
from humanize import naturaltime

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# HTTP utilities
# -------------------------------------------------------------------
async def fetch_json(url: str) -> dict:
    """Fetch JSON data asynchronously from URL."""
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.error(f"[fetch_json] {e}")
        return {}

async def fetch_html(url: str) -> str:
    """Fetch raw HTML text asynchronously from URL (used by Skywalker)."""
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url)
            r.raise_for_status()
            return r.text
    except Exception as e:
        logger.error(f"[fetch_html] {e}")
        return ""

# -------------------------------------------------------------------
# Telegram user utilities
# -------------------------------------------------------------------
def get_all_active_users():
    """Return all active Telegram user IDs from DB."""
    from db import get_session
    with get_session() as s:
        s.execute('SELECT telegram_id FROM "user" WHERE is_active=TRUE;')
        rows = s.fetchall()
    return [r["telegram_id"] for r in rows]

def _time_ago(dt):
    if not dt:
        return "N/A"
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return naturaltime(datetime.now(timezone.utc) - dt)

# -------------------------------------------------------------------
# Unified message builder
# -------------------------------------------------------------------
def _build_message(job):
    """Unified message formatter for all platforms."""
    title = job.get("title", "Untitled")
    platform = job.get("platform", "Unknown")
    keyword = job.get("matched_keyword", "-")
    desc = (job.get("description") or "-").strip()
    reqs = job.get("requirements", "-")
    created_at = job.get("created_at")

    budget_amt = job.get("budget_amount")
    budget_cur = job.get("budget_currency", "USD")
    usd_str = usd_line(budget_amt, budget_cur)

    budget_line = f"💰 Budget: {usd_str}"
    source_line = f"🌍 Source: {platform}"
    match_line = f"🔑 Match: {keyword}"
    posted_line = f"🕒 Posted: {_time_ago(created_at)}"

    text = (
        f"💼 {title}\n"
        f"{budget_line}\n"
        f"{source_line}\n"
        f"{match_line}\n"
        f"{posted_line}\n\n"
        f✏️ {desc}\n\n"
        f"📝 Requirements:\n{reqs}"
    )

    proposal_url = job.get("affiliate_url") or job.get("original_url")
    original_url = job.get("original_url")
    job_id = job.get("id")

    buttons = [
        [
            InlineKeyboardButton("🧾 Proposal", url=proposal_url or original_url or "https://freelancer.com"),
            InlineKeyboardButton("🔗 Original", url=original_url or proposal_url or "https://freelancer.com"),
        ],
        [
            InlineKeyboardButton("⭐ Save", callback_data=f"save:{job_id}"),
            InlineKeyboardButton("🗑 Delete", callback_data=f"delete:{job_id}"),
        ],
    ]

    return text, InlineKeyboardMarkup(buttons)

# -------------------------------------------------------------------
# Telegram sending
# -------------------------------------------------------------------
async def send_job_to_user(bot, user_id, job):
    """Send one job alert to a Telegram user."""
    try:
        text, markup = _build_message(job)
        await bot.send_message(chat_id=user_id, text=text, reply_markup=markup, disable_web_page_preview=False)
    except Exception as e:
        logger.warning(f"[send_job_to_user] Failed to send to {user_id}: {e}")

# -------------------------------------------------------------------
# Debug utility
# -------------------------------------------------------------------
if __name__ == "__main__":
    sample = {
        "title": "Test Job Example",
        "platform": "Freelancer",
        "matched_keyword": "logo",
        "description": "Design a modern logo for a tech startup.",
        "requirements": "Experience with Adobe Illustrator.",
        "budget_amount": 100,
        "budget_currency": "USD",
        "created_at": datetime.now(timezone.utc),
        "affiliate_url": "https://freelancer.com/projects/12345",
        "original_url": "https://freelancer.com/projects/12345",
        "id": 999,
    }
    msg, markup = _build_message(sample)
    print(msg)
    print("Buttons:", markup)
