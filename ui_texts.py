
def welcome_full(trial_days: int = 10) -> str:
    return f"""<b>👋 Welcome to Freelancer Alert Bot!</b>

🎁 You have a <b>{trial_days}-day free trial</b>.
Automatically finds matching freelance jobs from top platforms and sends you instant alerts.

Use <code>/help</code> to see how it works.
"""

def features_block() -> str:
    return """<b>✨ Features</b>
• Realtime job alerts (Freelancer API)
• Affiliate-wrapped <b>Proposal</b> & <b>Original</b> links
• Budget shown + USD conversion
• ⭐ Keep / 🗑 Delete buttons
• 10-day free trial, extend via admin
• Multi-keyword search (single/all modes)
• Platforms by country (incl. GR boards)
"""

HELP_EN = """<b>🧭 Help / How it works</b>

<b>1)</b> Add keywords with <code>/addkeyword</code> <i>python, telegram</i> (comma-separated, English or Greek).
<b>2)</b> Set your countries with <code>/setcountry</code> <i>US,UK</i> (or <i>ALL</i>).
<b>3)</b> Save a proposal template with <code>/setproposal &lt;text&gt;</code> —
placeholders: <code>{jobtitle}</code>, <code>{experience}</code>, <code>{stack}</code>, <code>{availability}</code>, <code>{step1}</code>, <code>{step2}</code>, <code>{step3}</code>, <code>{budgettime}</code>, <code>{portfolio}</code>, <code>{name}</code>.
<b>4)</b> When a job arrives you can: keep, delete, open <b>Proposal</b> or <b>Original</b> link.

<b>Use</b> <code>/mysettings</code> anytime. Try <code>/selftest</code> for a sample.
<b>/platforms</b> <i>CC</i> to see platforms by country (e.g., <code>/platforms GR</code>).
"""

def help_footer(hours: int = 24) -> str:
    return f"""
<b>🛰 Platforms monitored:</b>
• Global: <a href="https://www.freelancer.com">Freelancer.com</a> (affiliate links), PeoplePerHour, Malt, Workana, Guru, 99designs, Toptal*, Codeable*, YunoJuno*, Worksome*, twago, freelancermap
  <i>(* referral/curated platforms)</i>
• Greece: <a href="https://www.jobfind.gr">JobFind.gr</a>, <a href="https://www.skywalker.gr">Skywalker.gr</a>, <a href="https://www.kariera.gr">Kariera.gr</a>

<b>👑 Admin commands</b>:
<code>/users</code> — list users
<code>/grant &lt;telegram_id&gt; &lt;days&gt;</code> — extend license
<code>/block &lt;telegram_id&gt;</code> / <code>/unblock &lt;telegram_id&gt;</code>
<code>/broadcast &lt;text&gt;</code> — to all active
<code>/feedstatus</code> — last {hours}h by platform
"""

def settings_text(keywords, countries, proposal_template, trial_start, trial_end, license_until, active, blocked) -> str:
    def b(v): return "✅" if v else "❌"
    k = ", ".join(keywords) if keywords else "(none)"
    c = countries if countries else "ALL"
    pt = "(none)" if not proposal_template else "(saved)"
    ts = trial_start.isoformat().replace("+00:00", "Z") if trial_start else "—"
    te = trial_end.isoformat().replace("+00:00", "Z") if trial_end else "—"
    lic = "None" if not license_until else license_until.isoformat().replace("+00:00", "Z")

    return f"""<b>🛠 Your Settings</b>
• <b>Keywords:</b> {k}
• <b>Countries:</b> {c}
• <b>Proposal template:</b> {pt}

<b>●</b> Start date: {ts}
<b>●</b> Trial ends: {te} UTC
<b>🔑</b> License until: {lic}
<b>✅ Active:</b> {b(active)}    <b>⛔ Blocked:</b> {b(blocked)}

<b>🛰 Platforms monitored:</b>
• Global: <a href="https://www.freelancer.com">Freelancer.com</a> (affiliate links), PeoplePerHour, Malt, Workana, Guru, 99designs, Toptal*, Codeable*, YunoJuno*, Worksome*, twago, freelancermap
  <i>(* referral/curated platforms)</i>
• Greece: <a href="https://www.jobfind.gr">JobFind.gr</a>, <a href="https://www.skywalker.gr">Skywalker.gr</a>, <a href="https://www.kariera.gr">Kariera.gr</a>

<i>For extension, contact the admin.</i>"""
