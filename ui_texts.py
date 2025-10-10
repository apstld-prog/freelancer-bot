
from datetime import datetime
from typing import Optional

def welcome_card(trial_days:int=10)->str:
    return (
        "👋 <b>Welcome to Freelancer Alert Bot!</b>\n\n"
        f"🎁 You have a <b>{trial_days}-day free trial</b>.\n"
        "Automatically finds matching freelance jobs from top platforms\n"
        "and sends you instant alerts.\n\n"
        "Use <code>/help</code> to see how it works."
    )

def help_card()->str:
    return (
        "🧭 <b>Help / How it works</b>\n\n"
        "1) Add keywords with <code>/addkeyword</code> <code>python, telegram</code> (comma-\n"
        "   separated, English or Greek).\n"
        "2) Set your countries with <code>/setcountry</code> <code>US,UK</code> (or <b>ALL</b>).\n"
        "3) Save a proposal template with <code>/setproposal &lt;text&gt;</code> —\n"
        "   placeholders: <code>{jobtitle}</code>, <code>{experience}</code>, <code>{stack}</code>,\n"
        "   <code>{availability}</code>, <code>{step1}</code>, <code>{step2}</code>, <code>{step3}</code>,\n"
        "   <code>{budgettime}</code>, <code>{portfolio}</code>, <code>{name}</code>.\n"
        "4) When a job arrives you can: <b>keep</b>, <b>delete</b>, open <b>Proposal</b> or\n"
        "   <b>Original</b> link.\n\n"
        "Use <code>/mysettings</code> anytime to check your filters and proposal.\n"
        "Try <code>/selftest</code> for a sample.\n"
        "▶️ <code>/platforms</code> <i>CC</i> to see platforms by country (e.g., <code>/platforms GR</code>).\n\n"
        "🗂 <b>Platforms monitored:</b>\n"
        "• Global: <a href=\"https://www.freelancer.com\">Freelancer.com</a> (affiliate links), PeoplePerHour, Malt,\n"
        "  Workana, Guru, 99designs, Toptal*, Codeable*, YunoJuno*,\n"
        "  Worksome*, twago, freelancermap\n"
        "  (<i>* referral/curated platforms</i>)\n"
        "• Greece: <a href=\"https://www.jobfind.gr\">JobFind.gr</a>, <a href=\"https://www.skywalker.gr\">Skywalker.gr</a>, <a href=\"https://www.kariera.gr\">Kariera.gr</a>\n\n"
        "👑 <b>Admin commands</b>:\n"
        "/users — list users\n"
        "/grant &lt;telegram_id&gt; &lt;days&gt; — extend license\n"
        "/block &lt;telegram_id&gt; / /unblock &lt;telegram_id&gt;\n"
        "/broadcast &lt;text&gt; — send message to all active\n"
        "/feedstatus — show last 24h by platform"
    )

def mysettings_card(keywords:str, countries:str, proposal:str, active:bool, blocked:bool,
                    trial_start:Optional[datetime], trial_end:Optional[datetime], license_until:Optional[datetime])->str:
    def b(v:bool)->str: return "✅" if v else "❌"
    ts = trial_start.isoformat() if trial_start else "—"
    te = trial_end.isoformat() if trial_end else "—"
    lic = license_until.isoformat() if license_until else "None"
    return (
        "🛠️ <b>Your Settings</b>\n"
        f"• <b>Keywords:</b> {keywords}\n"
        f"• <b>Countries:</b> {countries}\n"
        f"• <b>Proposal template:</b> {proposal}\n\n"
        f"🟢 <b>Start date:</b> {ts}\n"
        f"🟢 <b>Trial ends:</b> {te} UTC\n"
        f"🟢 <b>License until:</b> {lic}\n\n"
        f"Active: {b(active)}   Blocked: {b(blocked)}\n\n"
        "🗂 <b>Platforms monitored:</b>\n"
        "• Global: <a href=\"https://www.freelancer.com\">Freelancer.com</a> (affiliate links), PeoplePerHour, Malt, Workana, Guru, 99designs, Toptal*, Codeable*, YunoJuno*, Worksome*, twago, freelancermap\n"
        "  (<i>* referral/curated platforms</i>)\n"
        "• Greece: <a href=\"https://www.jobfind.gr\">JobFind.gr</a>, <a href=\"https://www.skywalker.gr\">Skywalker.gr</a>, <a href=\"https://www.kariera.gr\">Kariera.gr</a>\n\n"
        "For extension, contact the admin."
    )
