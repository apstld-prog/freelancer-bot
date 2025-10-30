import os
import json
import logging
from datetime import datetime, timezone

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from currency_usd import usd_line
from humanize import naturaltime

logger = logging.getLogger(__name__)


# =========================================================
# HTTP utilities
# =========================================================
async def fetch_json(url: str, params: dict | None = None) -> dict:
    """Fetch JSON data asynchronously from URL with optional params."""
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            r = await client.get(url, params=params or {})
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.error(f"[fetch_json] {e}")
        return {}


async def fetch_html(url: str, params: dict | None = None) -> str:
    """Fetch raw HTML text asynchronously from URL (used by scrapers)."""
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            r = await client.get(url, params=params or {})
            r.raise_for_status()
            return r.text
    except Exception as e:
        logger.error(f"[fetch_html] {e}")
        return ""


# =========================================================
# Users & time helpers
# =========================================================
def get_all_active_users() -> list[dict]:
    """
    Return list of active users with telegram_id and keywords:
    [
      {"id": 1, "telegram_id": 5254..., "keywords": [{"keyword":"logo"}, ...]},
      ...
    ]
    """
    from db import get_session
    users: list[dict] = []
    with get_session() as s:
        s.execute('SELECT id, telegram_id FROM "user" WHERE is_active=TRUE AND telegram_id IS NOT NULL;')
        urows = s.fetchall()
        if not urows:
            return users

        ids = [r["id"] for r in urows]
        s.execute(
            """
            SELECT user_id, keyword
            FROM user_keywords
            WHERE user_id = ANY(%s)
            """,
            (ids,),
        )
        krows = s.fetchall()
        kw_by_user: dict[int, list[dict]] = {}
        for kr in krows:
            kw_by_user.setdefault(kr["user_id"], []).append({"keyword": kr["keyword"]})

        for r in urows:
            users.append(
                {
                    "id": r["id"],
                    "telegram_id": r["telegram_id"],
                    "keywords": kw_by_user.get(r["id"], []),
                }
            )
    return users


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


# =========================================================
# Message building
# =========================================================
def _build_markup(job: dict) -> InlineKeyboardMarkup:
    proposal_url = job.get("affiliate_url") or job.get("original_url")
    original_url = job.get("original_url") or proposal_url or "https://freelancer.com"
    job_id = job.get("id") or 0

    buttons = [
        [
            InlineKeyboardButton("🧾 Proposal", url=proposal_url or original_url),
            InlineKeyboardButton("🔗 Original", url=original_url),
        ],
        [
            InlineKeyboardButton("⭐ Save", callback_data=f"save:{job_id}"),
            InlineKeyboardButton("🗑 Delete", callback_data=f"delete:{job_id}"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def _build_message(job: dict) -> tuple[str, InlineKeyboardMarkup]:
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
        f"✏️ {desc}\n\n"
        f"📝 Requirements:\n{reqs}"
    )

    markup = _build_markup(job)
    return text, markup


# =========================================================
# Telegram sending (backward-compatible signature)
# =========================================================
async def send_job_to_user(*args):
    """
    Backward-compatible sender used by workers.

    Accepts either:
      1) (bot, user_id, job)                       -> build message from job
      2) (bot_or_none, user_id, message, job)      -> send given message, build markup from job if provided

    Uses HTTP API directly (no PTB bot required) if bot is None.
    """
    if len(args) < 3:
        raise TypeError("send_job_to_user expects (bot, user_id, job) or (bot, user_id, message, job)")

    # Parse arguments
    if len(args) == 3:
        bot, user_id, job = args
        text, markup = _build_message(job)
    else:
        bot, user_id, message, job = args[0], args[1], args[2], args[3]
        text = str(message)
        markup = _build_markup(job) if isinstance(job, dict) else None

    chat_id = int(user_id)

    # If a PTB bot instance is provided, use it
    if bot is not None:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=markup,
                parse_mode="HTML",
                disable_web_page_preview=False,
            )
            return
        except Exception as e:
            logger.warning(f"[send_job_to_user/PTB] Failed to send to {chat_id}: {e}")

    # Fallback: use Telegram HTTP API directly (token from env)
    token = (
        os.getenv("TELEGRAM_BOT_TOKEN")
        or os.getenv("BOT_TOKEN")
        or os.getenv("TELEGRAM_TOKEN")
    )
    if not token:
        logger.error("[send_job_to_user] No Telegram token in env (TELEGRAM_BOT_TOKEN/BOT_TOKEN/TELEGRAM_TOKEN)")
        return

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    if markup is not None:
        try:
            payload["reply_markup"] = json.dumps(markup.to_dict())
        except Exception:
            # In case InlineKeyboardMarkup serialization fails for any reason
            pass

    try:
        async with httpx.AsyncClient(timeout=25) as client:
            r = await client.post(f"https://api.telegram.org/bot{token}/sendMessage", data=payload)
            r.raise_for_status()
    except Exception as e:
        logger.warning(f"[send_job_to_user/HTTP] Failed to send to {chat_id}: {e}")


# =========================================================
# Local debug
# =========================================================
if __name__ == "__main__":
    sample = {
        "title": "Test Job Example",
        "platform": "Freelancer",
        "matched_keyword": "logo",
        "description": "Design a modern logo for a tech startup.",
        "requirements": "Experience with Adobe Illustrator.",
        "budget_amount": 150,
        "budget_currency": "USD",
        "created_at": datetime.now(timezone.utc),
        "affiliate_url": "https://freelancer.com/projects/12345",
        "original_url": "https://freelancer.com/projects/12345",
        "id": 999,
    }
    msg, mk = _build_message(sample)
    print(msg)
    print("Buttons:", mk.to_dict())
