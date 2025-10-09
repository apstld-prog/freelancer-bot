import os
import logging
from fastapi import FastAPI, Request, Response, HTTPException
from telegram import Update
from telegram.ext import Application
from bot import build_application

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("server")

# ==== ENV ====
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "hook-secret-777").strip()
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "").strip()  # π.χ. https://freelancer-bot-xxxxx.onrender.com

# ==== Build PTB application ====
app = FastAPI()
application: Application = build_application()

@app.on_event("startup")
async def on_startup():
    # Προαιρετικά ορίζουμε webhook αν έχει δοθεί base URL
    if WEBHOOK_BASE_URL:
        url = f"{WEBHOOK_BASE_URL.rstrip('/')}/webhook/{WEBHOOK_SECRET}"
        try:
            await application.bot.set_webhook(url=url, drop_pending_updates=True)
            log.info("Webhook set to %s", url)
        except Exception as e:
            log.exception("Failed to set webhook: %s", e)
    log.info("✅ Bot started via FastAPI")

@app.get("/")
async def root():
    return {"status": "ok"}

@app.post("/webhook/{secret}")
async def tg_webhook(secret: str, request: Request):
    # Έλεγχος μυστικού
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")

    # Ανάγνωση JSON του update
    try:
        data = await request.json()
    except Exception:
        # Telegram κάνει retry αν δεν δώσουμε 200 — εδώ δίνουμε 200 για ηρεμία,
        # αλλά λογκάρουμε το πρόβλημα
        log.exception("Invalid JSON body on webhook")
        return Response(status_code=200)

    # Δημιουργία Update αντικειμένου και προώθηση στο PTB
    try:
        update = Update.de_json(data=data, bot=application.bot)
        await application.process_update(update)
    except Exception:
        log.exception("Failed to process update")
        # Επιστρέφουμε 200 για να μη κάνει retry συνεχώς
        return Response(status_code=200)

    return Response(status_code=200)
