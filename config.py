import os
from dotenv import load_dotenv

# ✅ Φόρτωση περιβάλλοντος από .env ή Render Environment
load_dotenv()

# --- Core env ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    print("⚠️ BOT_TOKEN is empty! Please check Render environment variables.")

WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "hook-secret-777")
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///freelancer.db")

# Trial window (days)
TRIAL_DAYS = int(os.environ.get("TRIAL_DAYS", "10"))

# Admins (comma-separated ids)
ADMIN_IDS = {
    int(x)
    for x in os.environ.get("ADMIN_IDS", "5254014824").split(",")
    if x.strip().isdigit()
}

# Affiliate prefixes / ids
AFFILIATE_PREFIX_FREELANCER = os.environ.get(
    "AFFILIATE_PREFIX_FREELANCER", "https://www.freelancer.com/get/apstld?f=give"
)
AFFILIATE_PREFIX_GENERIC = os.environ.get("AFFILIATE_PREFIX_GENERIC", "")

# FX rates JSON string: {"EUR":1.08, "GBP":1.26, "USD":1.0}
FX_USD_RATES = os.environ.get("FX_USD_RATES", "")

# Platforms toggles (όλα ενεργά by default)
PLATFORMS = {
    "freelancer": os.environ.get("P_FREELANCER", "1") == "1",
    "peopleperhour": os.environ.get("P_PPH", "1") == "1",
    "malt": os.environ.get("P_MALT", "1") == "1",
    "workana": os.environ.get("P_WORKANA", "1") == "1",
    "wripple": os.environ.get("P_WRIPPLE", "1") == "1",
    "toptal": os.environ.get("P_TOPTAL", "1") == "1",
    "twago": os.environ.get("P_TWAGO", "1") == "1",
    "freelancermap": os.environ.get("P_FREELANCERMAP", "1") == "1",
    "yunoJuno": os.environ.get("P_YUNOJUNO", "1") == "1",
    "worksome": os.environ.get("P_WORKSOME", "1") == "1",
    "codeable": os.environ.get("P_CODEABLE", "1") == "1",
    "guru": os.environ.get("P_GURU", "1") == "1",
    "99designs": os.environ.get("P_99DESIGNS", "1") == "1",
    # Greece
    "jobfind": os.environ.get("P_JOBFIND", "1") == "1",
    "skywalker": os.environ.get("P_SKYWALKER", "1") == "1",
    "kariera": os.environ.get("P_KARIERA", "1") == "1",
    "careerjet": os.environ.get("P_CAREERJET", "1") == "1",
}

# Feeds and endpoints
SKYWALKER_RSS = os.environ.get("SKYWALKER_RSS", "https://www.skywalker.gr/jobs/feed")
CAREERJET_RSS = os.environ.get(
    "CAREERJET_RSS", "https://www.careerjet.gr/search/rss?l=Greece"
)
KARIERA_RSS = os.environ.get("KARIERA_RSS", "")

# Platform stats window
STATS_WINDOW_HOURS = int(os.environ.get("STATS_WINDOW_HOURS", "24"))
