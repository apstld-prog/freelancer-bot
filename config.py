import os

# === Telegram Bot ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "hook-secret-777")

# Render gives this automatically
RENDER_EXTERNAL_HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME", "")

# Database URL
DATABASE_URL = os.getenv("DATABASE_URL")

# Trial duration
TRIAL_DAYS = int(os.getenv("TRIAL_DAYS", "10"))

# Admin IDs
ADMIN_IDS = {
    int(x) for x in os.getenv("ADMIN_IDS", "5254014824").split(",") if x.strip().isdigit()
}

# Stats window
STATS_WINDOW_HOURS = int(os.getenv("STATS_WINDOW_HOURS", "24"))

# Worker interval
WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL", "180"))

# Keyword filter mode (on/off)
KEYWORD_FILTER_MODE = os.getenv("KEYWORD_FILTER_MODE", "on")
