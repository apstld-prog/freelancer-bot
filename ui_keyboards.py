
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    row1 = [
        InlineKeyboardButton("➕ Add Keywords", callback_data="add_keywords"),
        InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
    ]
    row2 = [
        InlineKeyboardButton("🆘 Help", callback_data="help"),
        InlineKeyboardButton("💾 Saved", callback_data="saved"),
    ]
    row3 = [InlineKeyboardButton("📨 Contact", callback_data="contact")]
    kb = [row1, row2, row3]
    if is_admin:
        kb.append([InlineKeyboardButton("🔥 Admin", callback_data="admin")])
    return InlineKeyboardMarkup(kb)

def job_action_kb(proposal_url: str, original_url: str) -> InlineKeyboardMarkup:
    row1 = [
        InlineKeyboardButton("📄 Proposal", url=proposal_url),
        InlineKeyboardButton("🔗 Original", url=original_url),
    ]
    row2 = [
        InlineKeyboardButton("⭐ Save", callback_data="job:save"),
        InlineKeyboardButton("🗑️ Delete", callback_data="job:delete"),
    ]
    return InlineKeyboardMarkup([row1, row2])
