
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

def job_action_kb(*args) -> InlineKeyboardMarkup:
    # Support both old signature (proposal_url, original_url) and new (original, proposal, affiliate)
    proposal_url = None
    original_url = None
    try:
        if len(args) >= 3:
            # (original, proposal, affiliate) from worker_runner
            original_url = args[0] or None
            proposal_url = args[1] or original_url
        elif len(args) >= 2:
            # (proposal, original) from handlers_jobs / selftest
            proposal_url = args[0] or None
            original_url = args[1] or None
        elif len(args) == 1:
            proposal_url = args[0] or None
    except Exception:
        pass

    row1 = [
        InlineKeyboardButton("📄 Proposal", url=proposal_url or original_url or ""),
        InlineKeyboardButton("🔗 Original", url=original_url or proposal_url or ""),
    ]
    row2 = [
        InlineKeyboardButton("⭐ Save", callback_data="job:save"),
        InlineKeyboardButton("🗑️ Delete", callback_data="job:delete"),
    ]
    return InlineKeyboardMarkup([row1, row2])
