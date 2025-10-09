"""
config.py — Global configuration for Freelancer Alert Bot
Environment-safe for both local and Render deployments.
"""

import os
from datetime import timedelta

# --------------------------------------------------
# Basic Telegram bot configuration
# --------------------------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = [
    int(x) for x in os.getenv("ADMIN_IDS", "5254014824").split(",") if x.strip().isdigit()
]

BOT_USERNAME = os.getenv("BOT_USERNAME", "@Freelancer_Alert_Jobs_bot")
BOT_NAME = os.getenv("BOT_NAME", "Freelancer Alert Jobs Bot")

# --------------------------------------------------
# Database configuration
# --------------------------------------------------
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/freelancer_bot"
)

# --------------------------------------------------
# Webhook / Server configuration
# --------------------------------------------------
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", f"/bot{BOT_TOKEN}")
WEBAPP_HOST = os.getenv("WEBAPP_HOST", "0.0.0.0")
WEBAPP_PORT = int(os.getenv("WEBAPP_PORT", "10000"))

# --------------------------------------------------
# Trial / Premium configuration
# --------------------------------------------------
TRIAL_DAYS = int(os.getenv("TRIAL_DAYS", "10"))
TRIAL_MESSAGE = os.getenv(
    "TRIAL_MESSAGE",
    "🎉 You have a 10-day free trial of Freelancer Alert Jobs Bot Premium!"
)

# --------------------------------------------------
# Job feed & worker settings
# --------------------------------------------------
FETCH_INTERVAL_SEC = int(os.getenv("FETCH_INTERVAL_SEC", "900"))  # 15 minutes
STATS_WINDOW_HOURS = int(os.getenv("STATS_WINDOW_HOURS", "24"))

# Affiliate prefix (for wrapped URLs, e.g. Freelancer.com affiliate)
AFFILIATE_PREFIX = os.getenv(
    "AFFILIATE_PREFIX",
    "https://www.freelancer.com/get/apstld?f=give&dl="
)

# List of supported job platforms (placeholders + live)
JOB_PLATFORMS = [
    "Skywalker",
    "Kariera",
    "Careerjet",
    "Freelancer",
    "PeoplePerHour",
    "Malt",
    "Workana",
    "Wripple",
    "Toptal",
    "twago",
    "freelancermap",
    "YunoJuno",
    "Worksome",
    "Codeable",
    "Guru",
    "99designs",
]

# --------------------------------------------------
# Logging / Debug
# --------------------------------------------------
DEBUG = bool(int(os.getenv("DEBUG", "1")))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# --------------------------------------------------
# Utility constants
# --------------------------------------------------
DEFAULT_TIMEZONE = os.getenv("DEFAULT_TIMEZONE", "UTC")
BOT_START_MESSAGE = os.getenv(
    "BOT_START_MESSAGE",
    "👋 Welcome to Freelancer Alert Jobs Bot!\n"
    "Set your keywords to start receiving job matches in real-time."
)

HELP_TEXT = os.getenv(
    "HELP_TEXT",
    "💡 Use /addkeyword to add new keywords separated by commas.\n"
    "Example: /addkeyword python, sales, logo\n\n"
    "You’ll receive job alerts matching your keywords from multiple platforms."
)

# --------------------------------------------------
# Internal paths (Render-safe)
# --------------------------------------------------
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(ROOT_DIR, "static")
BACKUP_DIR = os.path.join(ROOT_DIR, "backups")

# --------------------------------------------------
# Safe helper: ensure directories
# --------------------------------------------------
for path in (STATIC_DIR, BACKUP_DIR):
    os.makedirs(path, exist_ok=True)

# --------------------------------------------------
# Derived constants (timedeltas, etc.)
# --------------------------------------------------
TRIAL_PERIOD = timedelta(days=TRIAL_DAYS)
FETCH_INTERVAL = timedelta(seconds=FETCH_INTERVAL_SEC)
