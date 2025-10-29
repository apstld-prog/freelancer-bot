import logging
from datetime import datetime, timezone
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from currency_usd import usd_line
from humanize import naturaltime

logger = logging.getLogger(__name__)

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

def _build_message(job):
    """Unified message formatter for all platforms"""
    title = job.get("title", "Untitled")
    platform = job.get("platform", "Unknown")
    keyword = job.get("matched_keyword", "-")
    desc = job.get("description", "-").strip()
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
