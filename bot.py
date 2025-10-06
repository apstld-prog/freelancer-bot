# bot.py
# Telegram bot entrypoint with /feedsstatus + 🔄 Refresh (admin only)

import logging
import os
import asyncio
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# === Εισάγουμε τον νέο handler για τα στατιστικά feeds ===
from feedsstatus_handler import register_feedsstatus_handler

# === Logging configuration ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [bot] %(levelname)s: %(message)s",
)
log = logging.getLogger("bot")

# === Περιβάλλον ===
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "hook-secret-777")
ADMIN_TG_ID = os.getenv("ADMIN_TG_ID", "")  # Admin Telegram ID

# === Δημιουργία εφαρμογής ===
def build_application() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()

    # --- /start ---
    async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        await update.message.reply_text(
            f"👋 Hello {user.first_name or ''}! "
            f"This bot is online and ready.\n\n"
            f"Use /selftest to check status."
        )

    # --- /selftest ---
    async def selftest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("✅ Bot is active and responding normally!")

    # --- Register basic handlers ---
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("selftest", selftest_cmd))

    # --- ΝΕΟ: Εγγραφή του admin-only /feedsstatus με κουμπί 🔄 ---
    register_feedsstatus_handler(app)

    return app


# === Εκκίνηση σε webhook mode ===
if __name__ == "__main__":
    app = build_application()

    async def run():
        await app.initialize()
        await app.start()

        # Webhook ρύθμιση (αν χρησιμοποιείς Render)
        webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME', 'yourdomain.com')}/webhook/{WEBHOOK_SECRET}"
        await app.bot.set_webhook(
            url=webhook_url,
            allowed_updates=Update.ALL_TYPES,
        )

        log.info("✅ Bot started successfully.")
        log.info(f"Webhook URL: {webhook_url}")
        log.info("Press Ctrl+C to stop.")
        await asyncio.Event().wait()

    try:
        asyncio.run(run())
    except (KeyboardInterrupt, SystemExit):
        log.info("Bot stopped manually.")
