from datetime import datetime, timezone
from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from ui_keyboards import job_action_kb

def _relative_now_english(dt: datetime) -> str:
    # We assume the card is sent immediately; so "just now" is correct.
    # If later we pass a real posted timestamp, this function will still format it.
    now = datetime.now(timezone.utc)
    # Ensure timezone-aware
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    diff = int((now - dt).total_seconds())
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

async def send_job_card(bot, chat_id: int, text: str, proposal_url: str, original_url: str):
    # Append a relative "Posted ..." line under the description (at send time)
    posted_line = f"\n🕓 Posted {_relative_now_english(datetime.now(timezone.utc))}"
    text_with_time = f"{text.rstrip()}\n{posted_line}"
    kb = job_action_kb(proposal_url, original_url)
    await bot.send_message(chat_id=chat_id, text=text_with_time, parse_mode="HTML", reply_markup=kb)
