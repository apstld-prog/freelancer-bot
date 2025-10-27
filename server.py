# server.py — FastAPI + Telegram webhook server
# Σταθερό ensure_admin_user για τον πίνακα "user" (όχι "users")

import os
import logging
from typing import Any, Dict

from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy import text

from bot import build_application  # μην αλλάξεις την υπογραφή
from db import get_session

log = logging.getLogger("server")
logging.basicConfig(level=logging.INFO)

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "hook-secret-777")
BOT_BASE_PATH = os.getenv("BOT_BASE_PATH", "/webhook")
ADMIN_TELEGRAM_ID_ENV = os.getenv("ADMIN_TELEGRAM_ID", "")
try:
    ADMIN_TELEGRAM_ID = int(ADMIN_TELEGRAM_ID_ENV) if ADMIN_TELEGRAM_ID_ENV else 5254014824
except Exception:
    ADMIN_TELEGRAM_ID = 5254014824

# -----------------------------------------------------------------------------
# Build Telegram application once
# -----------------------------------------------------------------------------
app_tg = build_application()

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def ensure_admin_user() -> None:
    """
    Εξασφαλίζει ότι στον ΠΙΝΑΚΑ "user" υπάρχει admin row με telegram_id = ADMIN_TELEGRAM_ID.
    Αν υπάρχει -> UPDATE βασικών πεδίων.
    Αν δεν υπάρχει -> INSERT με ΠΛΗΡΩΣ ΣΥΜΠΛΗΡΩΜΕΝΑ πεδία (για να μην σκάσουν NOT NULL).
    Δεν χρησιμοποιούμε ON CONFLICT σε λάθος constraint. Κάνουμε καθαρό SELECT -> UPDATE/INSERT.
    """
    tid = ADMIN_TELEGRAM_ID
    username = "admin"

    with get_session() as s:
        # Υπάρχει ήδη admin με αυτό το telegram_id;
        row = s.execute(
            text('SELECT id FROM "user" WHERE telegram_id = :tid LIMIT 1'),
            {"tid": tid},
        ).fetchone()

        if row:
            # Απλό UPDATE των σημαντικών σημάτων πρόσβασης + updated_at
            s.execute(
                text(
                    '''
                    UPDATE "user"
                    SET
                        username = :username,
                        is_admin = TRUE,
                        is_active = TRUE,
                        is_blocked = FALSE,
                        updated_at = NOW() AT TIME ZONE 'UTC'
                    WHERE telegram_id = :tid
                    '''
                ),
                {"tid": tid, "username": username},
            )
            s.commit()
            log.info("✅ Admin already present in table \"user\" — updated flags.")
            return

        # Δεν υπάρχει: κάνε πλήρες INSERT με όλα τα κρίσιμα πεδία.
        # Για να μην σκάνε NOT NULL: γεμίζουμε is_blocked, is_active, is_admin, created_at, updated_at.
        s.execute(
            text(
                '''
                INSERT INTO "user" (
                    id,
                    telegram_id,
                    username,
                    is_admin,
                    is_active,
                    is_blocked,
                    created_at,
                    updated_at
                )
                VALUES (
                    :id,
                    :tid,
                    :username,
                    TRUE,
                    TRUE,
                    FALSE,
                    NOW() AT TIME ZONE 'UTC',
                    NOW() AT TIME ZONE 'UTC'
                )
                '''
            ),
            {"id": tid, "tid": tid, "username": username},
        )
        s.commit()
        log.info('✅ Admin inserted into table "user".')

# -----------------------------------------------------------------------------
# FastAPI
# -----------------------------------------------------------------------------
app = FastAPI()

@app.get("/", response_class=PlainTextResponse)
async def root() -> str:
    return "Freelancer Bot is running."

@app.on_event("startup")
async def on_startup() -> None:
    """
    Εκτελείται κατά την εκκίνηση του FastAPI server.
    Εξασφαλίζει ότι υπάρχει admin στον πίνακα 'user'
    και προετοιμάζει το Telegram webhook.
    """
    try:
        ensure_admin_user()
        log.info("✅ Admin ensured successfully in table \"user\".")
    except Exception as e:
        log.exception("Failed to ensure admin user in table \"user\": %s", e)

    # Προετοιμασία Telegram bot
    try:
        log.info("Application.initialize() done")
    except Exception as e:
        log.exception("Failed during Telegram app init: %s", e)

@app.post(f"{BOT_BASE_PATH}/{WEBHOOK_SECRET}")
async def telegram_webhook(req: Request) -> Response:
    """
    Λαμβάνει τα updates από το Telegram και τα περνάει στην PTB Application.
    """
    try:
        payload: Dict[str, Any] = await req.json()
    except Exception:
        payload = {}

    chat = None
    text_msg = None
    try:
        message = payload.get("message") or payload.get("edited_message") \
                  or payload.get("channel_post") or {}
        chat = (message.get("chat") or {}).get("id")
        text_msg = message.get("text")
    except Exception:
        pass

    log.info("Incoming message: chat=%s text=%s", chat, text_msg)

    # Προώθηση του update στην ουρά PTB
    try:
        await app_tg.update_queue.put(payload)
    except Exception as e:
        log.exception("Failed to enqueue update: %s", e)

    return Response(status_code=200)

@app.get("/healthz", response_class=PlainTextResponse)
async def health() -> str:
    """Health check endpoint."""
    return "ok"
