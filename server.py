# server.py
import os
import logging
from fastapi import FastAPI, Request, Response
from telegram.ext import Application
from bot import build_application  # ΔΕΝ αλλάζω τίποτα στο bot.py

logger = logging.getLogger("server")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

# Ρυθμίσεις
PUBLIC_URL = os.getenv("PUBLIC_URL")  # π.χ. https://freelancer-bot-ns7s.onrender.com
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "hook-secret-777")

# Φτιάχνουμε την PTB εφαρμογή όπως ήδη τη χτίζεις στο bot.py
application: Application = build_application()

app = FastAPI()


@app.get("/")
async def root() -> Response:
    return Response("OK", media_type="text/plain")


@app.post(f"/webhook/{WEBHOOK_SECRET}")
async def telegram_webhook(req: Request):
    """
    ΔΕΝ κάνουμε parsing εδώ. Παίρνουμε raw JSON και το περνάμε στο update_queue.
    Αν κάτι πάει στραβά, log και ΠΑΝΤΑ 200 ώστε το Telegram να μη θεωρεί αποτυχία.
    """
    try:
        update_json = await req.json()
        await application.update_queue.put(update_json)
        return {"ok": True}
    except Exception:
        logger.exception("Webhook handler crashed — swallowing and returning 200.")
        return {"ok": True}


@app.on_event("startup")
async def on_startup():
    # Εκκίνηση PTB
    await application.initialize()
    await application.start()

    # Ορισμός webhook αν έχουμε PUBLIC_URL
    try:
        if PUBLIC_URL:
            await application.bot.delete_webhook()
            url = f"{PUBLIC_URL}/webhook/{WEBHOOK_SECRET}"
            await application.bot.set_webhook(url=url)
            logger.info("Webhook set to %s", url)
        else:
            logger.warning("PUBLIC_URL not set — webhook not configured.")
    except Exception:
        logger.exception("Failed to set webhook on startup.")


@app.on_event("shutdown")
async def on_shutdown():
    # Καθαρό shutdown PTB
    try:
        await application.stop()
        await application.shutdown()
    except Exception:
        logger.exception("PTB shutdown error")
