# ==========================================================
# UI Texts for Freelancer Alert Bot — template pack (v1)
# Matches the screenshots, keeps our recent additions.
# ==========================================================

def welcome_full(days: int) -> str:
    return (
        "👋 <b>Welcome to Freelancer Alert Bot!</b>\n\n"
        "🎁 You have a <b>{days}-day free trial</b>.\n"
        "Automatically finds matching freelance jobs from top\n"
        "platforms and sends you instant alerts.\n\n"
        "Use <code>/help</code> to see how it works.\n\n"
        "➕ Add Keywords          ⚙️ Settings\n"
        "🆘 Help                   💾 Saved\n"
        "📨 Contact               🔥 Admin"
    ).format(days=days)


def help_footer(hours: int, admin: bool = False) -> str:
    if not admin:
        return (
            "\n\n<b>✨ Features</b>\n"
            "• Realtime job alerts (Freelancer API)\n"
            "• Affiliate-wrapped Proposal & Original links\n"
            "• Budget shown + USD conversion\n"
            "• ⭐ Keep / 🗑 Delete buttons\n"
            "• {trial} free trial, extend via admin\n"
            "• Multi-keyword search (single/all modes)\n"
            "• Platforms by country (incl. GR boards)\n\n"
            "<b>🗺 Platforms monitored:</b>\n"
            "Global: <i>Freelancer.com</i> (affiliate links), PeoplePerHour, Malt, Workana, Guru, 99designs, Toptal*, Codeable*, YunoJuno*, Worksome*, twago, freelancermap\n"
            "Greece: JobFind.gr, Skywalker.gr, Kariera.gr"
        ).format(trial="10-day")
    # Admin footer (HTML-safe with code block)
    return (
        "\n\n<b>✨ Features</b>\n"
        "• Realtime job alerts (Freelancer API)\n"
        "• Affiliate-wrapped Proposal & Original links\n"
        "• Budget shown + USD conversion\n"
        "• ⭐ Keep / 🗑 Delete buttons\n"
        "• {trial} free trial, extend via admin\n"
        "• Multi-keyword search (single/all modes)\n"
        "• Platforms by country (incl. GR boards)\n\n"
        "<b>🗺 Platforms monitored:</b>\n"
        "Global: <i>Freelancer.com</i> (affiliate links), PeoplePerHour, Malt, Workana, Guru, 99designs, Toptal*, Codeable*, YunoJuno*, Worksome*, twago, freelancermap\n"
        "Greece: JobFind.gr, Skywalker.gr, Kariera.gr\n\n"
        "<b>👑 Admin commands</b>\n"
        "<code>"
        "/users — list users\n"
        "/grant &lt;telegram_id&gt; &lt;days&gt;\n"
        "/block &lt;telegram_id&gt; / /unblock &lt;telegram_id&gt;\n"
        "/broadcast &lt;text&gt;\n"
        f"/feedstatus — show last {hours}h per platform"
        "</code>"
    ).format(trial="10-day")
