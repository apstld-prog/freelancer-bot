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
    """Footer με admin εντολές – ασφαλές για HTML parse_mode."""
    if not admin:
        return ""
    return (
        "\n\n<b>👑 Admin commands</b>\n"
        "<code>"
        "/users\n"
        "/grant &lt;telegram_id&gt; &lt;days&gt;\n"
        "/block &lt;telegram_id&gt; / /unblock &lt;telegram_id&gt;\n"
        "/broadcast &lt;text&gt;\n"
        f"/feedstatus — show last {hours}h per platform"
        "</code>"
    )
