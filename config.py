import os

# --- Core env ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
TELEGRAM_BOT_TOKEN = BOT_TOKEN  # âœ… for worker compatibility
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "hook-secret-777")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///freelancer.db")

# Trial window (days)
TRIAL_DAYS = int(os.getenv("TRIAL_DAYS", "10"))

# Admins (comma-separated ids)
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "5254014824").split(",") if x.strip().isdigit()}

# Affiliate prefixes / ids
AFFILIATE_PREFIX_FREELANCER = os.getenv("AFFILIATE_PREFIX_FREELANCER", "https://www.freelancer.com/get/apstld?f=give")
AFFILIATE_PREFIX_GENERIC = os.getenv("AFFILIATE_PREFIX_GENERIC", "")

# FX rates JSON string: {"EUR":1.08, "GBP":1.26, "USD":1.0}
FX_USD_RATES = os.getenv("FX_USD_RATES", "")

# Platforms toggles (all on by default)
PLATFORMS = {
    "freelancer": os.getenv("P_FREELANCER", "1") == "1",
    "peopleperhour": os.getenv("P_PPH", "1") == "1",
    "malt": os.getenv("P_MALT", "1") == "1",
    "workana": os.getenv("P_WORKANA", "1") == "1",
    "wripple": os.getenv("P_WRIPPLE", "1") == "1",
    "toptal": os.getenv("P_TOPTAL", "1") == "1",
    "twago": os.getenv("P_TWAGO", "1") == "1",
    "freelancermap": os.getenv("P_FREELANCERMAP", "1") == "1",
    "yunoJuno": os.getenv("P_YUNOJUNO", "1") == "1",
    "worksome": os.getenv("P_WORKSOME", "1") == "1",
    "codeable": os.getenv("P_CODEABLE", "1") == "1",
    "guru": os.getenv("P_GURU", "1") == "1",
    "99designs": os.getenv("P_99DESIGNS", "1") == "1",
    # Greece
    "jobfind": os.getenv("P_JOBFIND", "1") == "1",
    "skywalker": os.getenv("P_SKYWALKER", "1") == "1",
    "kariera": os.getenv("P_KARIERA", "1") == "1",
    "careerjet": os.getenv("P_CAREERJET", "1") == "1",
}

# Feeds and endpoints
SKYWALKER_RSS = os.getenv("SKYWALKER_RSS", "https://www.skywalker.gr/jobs/feed")
CAREERJET_RSS = os.getenv("CAREERJET_RSS", "https://www.careerjet.gr/search/rss?l=Greece")
KARIERA_RSS = os.getenv("KARIERA_RSS", "")

# Platform stats window
STATS_WINDOW_HOURS = int(os.getenv("STATS_WINDOW_HOURS", "24"))

# âœ… Worker timing (fix ImportError)
WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL", "120"))




