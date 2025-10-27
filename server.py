import os
import logging
from fastapi import FastAPI, Request, Response, HTTPException
from telegram import Update
from telegram.ext import Application
from sqlalchemy import text

from db import get_session
from bot import build_application  # δεν πειράζω bot.py/στήσιμο

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("server")

# --------- Config / ENV ----------
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "hook-secret-777").strip()
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "").strip()

# Admin (προαιρετικά από ENV, αλλιώς τα δικά σου defaults)
ADMIN_TG_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "5254014824"))
ADMIN_USERS_ID = int(os.getenv("ADMIN_USERS_ID", "1"))

# --------- FastAPI & Telegram Application ----------
app = FastAPI()
application: Application = build_application()

_is_initialized = False
_is_started = False


def ensure_admin_user():
    """
    Εξασφαλίζει ότι υπάρχει admin και στα δύο tables:
      - users (το «νέο»/κύριο)
      - "user" (legacy/παράλληλο)
    Χωρίς conflicts/unique violations, χωρίς nulls.
    """
    try:
        with get_session() as s:
            # === 1) USERS table (κύριο) ===
            # Upsert με conflict στο PRIM KEY id (ADMIN_USERS_ID).
            # Γεμίζουμε και created_at/updated_at για να μην έχουμε NOT NULL.
            s.execute(text("""
                INSERT INTO users (
                    id, telegram_id, is_admin, is_active, is_blocked,
                    started_at, created_at, updated_at
                )
                VALUES (
                    :id, :tg, TRUE, TRUE, FALSE,
                    NOW() AT TIME ZONE 'UTC',
                    NOW() AT TIME ZONE 'UTC',
                    NOW() AT TIME ZONE 'UTC'
                )
                ON CONFLICT (id) DO UPDATE SET
                    telegram_id = EXCLUDED.telegram_id,
                    is_admin = TRUE,
                    is_active = TRUE,
                    is_blocked = FALSE,
                    updated_at = NOW() AT TIME ZONE 'UTC';
            """), {"id": ADMIN_USERS_ID, "tg": ADMIN_TG_ID})

            # === 2) "user" table (legacy) ===
            # Εδώ χρησιμοποιούμε ON CONFLICT (telegram_id) για να μην «τρακάρει»
            # στο μοναδικό index ix_user_telegram_id που έχεις.
            # Βάζουμε και updated_at για να μην χτυπάει NOT NULL.
            s.execute(text("""
                INSERT INTO "user" (
                    id, telegram_id, username, is_admin, is_active, is_blocked,
                    created_at, updated_at
                )
                VALUES (
                    :tg, :tg, 'admin', TRUE, TRUE, FALSE,
                    NOW() AT TIME ZONE 'UTC',
                    NOW() AT TIME ZONE 'UTC'
                )
                ON CONFLICT (telegram_id) DO UPDATE SET
                    username  = EXCLUDED.username,
                    is_admin  = TRUE,
                    is_active = TRUE,
                    is_blocked= FALSE,
                    updated_at= NOW() AT TIME ZONE 'UTC';
            """), {"tg": ADMIN_TG_ID})

            s.commit()
            log.info("✅ Admin ensured successfully in both tables.")
    except Exception as e:
        log.exception("Failed to ensure admin user: %s", e)


@app.on_event("startup")
async def on_startup():
    global _is_initialized, _is_started
    try:
        # Δεν αλλάζω το flow σου — παραμένει όπως το έχεις
        os.system("python3 init_users.py")
        os.system("python3 init_keywords.py")

        # Ασφάλεια admin μετά τα init scripts
        ensure_admin_user()

        if not _is_initialized:
            await application.initialize()
            _is_initialized = True
            log.info("Application.initialize() done")

        if not _is_started:
            await application.start()
            _is_started = True
            log.info("Application.start() done")

        if WEBHOOK_BASE_URL:
            url = f"{WEBHOOK_BASE_URL.rstrip('/')}/webhook/{WEBHOOK_SECRET}"
            await application.bot.set_webhook(
                url=url,
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query"],
            )
            log.info("Webhook set to %s", url)

        log.info("✅ Bot started via FastAPI")
    except Exception:
        log.exception("Startup failed")


@app.on_event("shutdown")
async def on_shutdown():
    global _is_initialized, _is_started
    try:
        if _is_started:
            await application.stop()
            _is_started = False
            log.info("Application.stop() done")

        if _is_initialized:
            await application.shutdown()
            _is_initialized = False
            log.info("Application.shutdown() done")
    except Exception:
        log.exception("Shutdown failed")


@app.get("/")
async def root():
    return {"status": "ok"}


@app.post("/webhook/{secret}")
async def tg_webhook(secret: str, request: Request):
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")

    try:
        data = await request.json()
    except Exception:
        log.exception("Invalid JSON body on webhook")
        return Response(status_code=200)

    try:
        if "message" in data:
            msg = data["message"]
            log.info("Incoming message: chat=%s text=%s",
                     msg.get("chat", {}).get("id"),
                     msg.get("text"))
        if "callback_query" in data:
            cq = data["callback_query"]
            log.info("Incoming callback: from=%s data=%s",
                     cq.get("from", {}).get("id"),
                     cq.get("data"))
    except Exception:
        pass

    try:
        global _is_initialized, _is_started
        if not _is_initialized:
            await application.initialize()
            _is_initialized = True
            log.info("Re-initialize Application in webhook")
        if not _is_started:
            await application.start()
            _is_started = True
            log.info("Re-start Application in webhook")

        update = Update.de_json(data=data, bot=application.bot)
        await application.process_update(update)
    except Exception:
        log.exception("Failed to process update")
        return Response(status_code=200)

    return Response(status_code=200)
