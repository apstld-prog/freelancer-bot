from datetime import datetime, timezone
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# --- helper για relative time σε αγγλική μορφή ---
def format_relative_time(ts):
    if not ts:
        return "just now"
    now = datetime.now(timezone.utc)
    diff = now - ts

    secs = int(diff.total_seconds())
    if secs < 60:
        return "just now"
    mins = secs // 60
    if mins < 60:
        return f"{mins} minute{'s' if mins != 1 else ''} ago"
    hours = mins // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    return f"{days} day{'s' if days != 1 else ''} ago"


# --- κύρια συνάρτηση αποστολής αγγελίας ---
async def send_job_card(bot, chat_id, title, description, url, created_at=None):
    """
    Στέλνει κάρτα αγγελίας στον χρήστη με inline κουμπιά και σχετική ώρα.
    """
    # Υπολογισμός σχετικής ώρας (π.χ. "Posted 2 hours ago")
    rel_time = format_relative_time(created_at)
    posted_line = f"\n🕓 Posted {rel_time}"

    text = f"*{title.strip()}*\n\n{description.strip() if description else ''}{posted_line}"

    kb = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("🔗 View Job", url=url),
            InlineKeyboardButton("💾 Save", callback_data="job:save"),
        ]]
    )

    await bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=kb,
    )
