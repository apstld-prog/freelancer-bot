# ================= UI TEXTS (RESET PACK v0) =================
def welcome_full(days: int) -> str:
    return (
        "👋 <b>Welcome to Freelancer Alert Bot!</b>\n"
        "🎁 You have a <b>{days}-day free trial</b>.\n"
        "Automatically finds matching freelance jobs from top\n"
        "platforms and sends you instant alerts.\n\n"
        "Use <code>/help</code> to see how it works."
    ).format(days=days)

def help_footer(hours: int, admin: bool = False) -> str:
    base = (
        "\n\n<b>✨ Features</b>\n"
        "• Realtime job alerts (Freelancer API)\n"
        "• Affiliate-wrapped Proposal & Original links\n"
        "• Budget shown + USD conversion\n"
        "• ⭐ Keep / 🗑 Delete buttons\n"
        "• 10-day free trial, extend via admin\n"
        "• Multi-keyword search (single/all modes)\n"
        "• Platforms by country (incl. GR boards)"
    )
    if not admin:
        return base
    admin_block = (
        "\n\n<b>👑 Admin commands</b>\n"
        "<code>"
        "/users — list users\n"
        "/grant &lt;telegram_id&gt; &lt;days&gt;\n"
        "/block &lt;telegram_id&gt; / /unblock &lt;telegram_id&gt;\n"
        "/broadcast &lt;text&gt;\n"
        f"/feedstatus — show last {hours}h per platform"
        "</code>"
    )
    return base + admin_block
