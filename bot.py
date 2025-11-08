import asyncio
from telegram.ext import ApplicationBuilder
from config import BOT_TOKEN

from handlers_start import setup as setup_start
from handlers_ui import setup as setup_ui
from handlers_help import setup as setup_help
from handlers_settings import setup as setup_settings
from handlers_jobs import setup as setup_jobs

def build_application():
    return application

application = ApplicationBuilder().token(BOT_TOKEN).build()

setup_start(application)
setup_ui(application)
setup_help(application)
setup_settings(application)
setup_jobs(application)

async def main():
    await application.initialize()
    await application.start()
    print("✅ Telegram bot running in webhook mode")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
