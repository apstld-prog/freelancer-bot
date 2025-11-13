# bot.py — FULL BUILD, WEBHOOK-ONLY, HANDLER LOADER

import os
import logging
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

# === IMPORT HANDLERS (from your uploaded files) ===
from handlers_start import register_start_handlers
from handlers_ui import register_ui_handlers
from handlers_settings import register_settings_handlers
from handlers_help import register_help_handlers
from handlers_admin import register_admin_handlers
from handlers_jobs import register_jobs_handlers

# === ENVIRONMENT ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("❌ TELEGRAM_BOT_TOKEN missing")

# === LOGGER ===
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("bot")

# =====================================================
#  BUILD APPLICATION
# =====================================================
def build_application():
    app = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
        .read_timeout(30)
        .write_timeout(30)
        .connect_timeout(30)
        .pool_timeout(30)
        .build()
    )

    # REGISTER HANDLERS  
    register_start_handlers(app)
    register_ui_handlers(app)
    register_settings_handlers(app)
    register_help_handlers(app)
    register_admin_handlers(app)
    register_jobs_handlers(app)

    return app


# =====================================================
#  ENTRYPOINT (used by server.py)
# =====================================================
app = build_application()

