# ==========================================================
# UI Texts for Freelancer Alert Bot
# ==========================================================

def welcome_full(days: int) -> str:
    return (
        f"👋 <b>Welcome!</b>\n"
        f"You have <b>{days}-day free trial</b> active.\n"
        f"Use the menu below to manage your keyword alerts.\n\n"
        "💡 Tip: Add keywords to start receiving job notifications!"
    )


def help_footer(hours: int, admin: bool = False) -> str:
    """Footer with optional admin commands."""
    block = f"""
\n\n<b>👑 Admin commands</b>
/users — list users
/grant <telegram_id> <days>
/block <telegram_id> / /unblock <telegram_id>
/broadcast <text>
/feedstatus — show last {hours}h per platform
"""
    return block if admin else ""
