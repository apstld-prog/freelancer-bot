from datetime import datetime, timezone
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def _relative_english(ts: datetime | None) -> str:
    if not ts:
        return "just now"
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    diff = int((now - ts).total_seconds())
    if diff < 60:
        return "just now"
    mins = diff // 60
    if mins < 60:
        return f"{mins} minute{'s' if mins != 1 else ''} ago"
    hours = mins // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    return f"{days} day{'s' if days != 1 else ''} ago"

async def send_job_card(bot, chat_id: int, title: str, description: str, url: str, created_at: datetime | None = None):
    """
    Sends a job card exactly like before, plus a relative posted-time line under the description.
    NOTE: If your worker doesn't pass created_at, it will show 'just now' at send time.
    """
    posted_line = f"\n🕓 Posted {_relative_english(created_at)}"
    text = f"*{title.strip()}*\n\n{(description or '').strip()}{posted_line}"

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔗 View Job", url=url),
        InlineKeyboardButton("💾 Save", callback_data="job:save"),
    ]])

    await bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=kb,
    )
