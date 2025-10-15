import logging
import os
import psycopg2
import html
import requests
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from fastapi import FastAPI, Request
from threading import Thread
import uvicorn

# ==========================================================
# CONFIG
# ==========================================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "hook-secret-777")
WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL", "https://freelancer-bot-ns7s.onrender.com") + f"/webhook/{WEBHOOK_SECRET}"
DB_URL_RAW = os.getenv("DATABASE_URL", "")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

# ==========================================================
# DB URL NORMALIZATION (fix for psycopg2)
# ==========================================================
def normalize_db_url(url: str) -> str:
    if not url:
        return url
    # Render/SQLAlchemy styles to psycopg2 DSN:
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql+psycopg2://"):
        url = "postgresql://" + url[len("postgresql+psycopg2://"):]
    return url

DB_URL = normalize_db_url(DB_URL_RAW)

# ==========================================================
# DATABASE
# ==========================================================
def get_connection():
    # psycopg2 wants a plain DSN
    return psycopg2.connect(DB_URL, sslmode="require")

# ==========================================================
# START COMMAND
# ==========================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    tg_id = user.id
    name = user.first_name or "User"

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO "user"(telegram_id, first_name) VALUES (%s, %s) ON CONFLICT (telegram_id) DO NOTHING;',
        (tg_id, name),
    )
    conn.commit()
    conn.close()

    keyboard = [
        [InlineKeyboardButton("🔍 Search Jobs", callback_data="act:search")],
        [InlineKeyboardButton("💾 Saved Jobs", callback_data="act:saved")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="act:help")],
        [InlineKeyboardButton("🧩 Debug", callback_data="act:debug")],
    ]
    if update.message:
        await update.message.reply_text(
            f"👋 Hello {html.escape(name)}!\nWelcome to Freelancer Alerts Bot.\n\nChoose an option:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    else:
        # in case /start came as callback (rare)
        await update.effective_chat.send_message(
            f"👋 Hello {html.escape(name)}!\nWelcome to Freelancer Alerts Bot.\n\nChoose an option:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

# ==========================================================
# SEARCH HANDLERS
# ==========================================================
async def handle_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("Please send me a keyword to search for jobs.")

async def handle_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyword = (update.message.text or "").strip()
    if not keyword:
        return await update.message.reply_text("Please type a valid keyword.")

    url = f"https://www.freelancer.com/api/projects/0.1/projects/active/?query={keyword}&limit=5"
    r = requests.get(url, timeout=20)
    data = r.json() if r.ok else {}

    if "result" not in data or not data["result"].get("projects"):
        return await update.message.reply_text("No jobs found for that keyword.")

    jobs = data["result"]["projects"]
    conn = get_connection()
    cur = conn.cursor()

    for job in jobs:
        title = job.get("title", "No title")
        desc = job.get("preview_description", "")
        link = f"https://www.freelancer.com/projects/{job.get('seo_url','')}"
        budget = job.get("budget", {}) or {}
        currency = (budget.get("currency") or {}).get("code", "")
        amount = f"{budget.get('minimum', 0)}-{budget.get('maximum', 0)} {currency}"

        # Store minimal job_event row if not exists
        try:
            cur.execute(
                """
                INSERT INTO job_event (platform, title, description, original_url, budget_currency, budget_amount)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING;
                """,
                ("freelancer", title, desc, link, currency, amount),
            )
        except Exception:
            pass

        keyboard = [
            [
                InlineKeyboardButton("💾 Save", callback_data=f"job:save|{link}"),
                InlineKeyboardButton("🌐 Open", url=link),
            ]
        ]
        await update.message.reply_text(
            f"💼 {title}\n💰 {amount}\n🔗 {link}",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    conn.commit()
    conn.close()

# ==========================================================
# CALLBACK HANDLER
# ==========================================================
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    tg_id = q.from_user.id

    conn = get_connection()
    cur = conn.cursor()
    cur.execute('SELECT id FROM "user" WHERE telegram_id=%s;', (tg_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return await q.message.reply_text("Please use /start first.")
    user_id = row[0]

    # SAVE JOB
    if data.startswith("job:save|"):
        job_link = data.split("|", 1)[1]
        try:
            cur.execute(
                """
                INSERT INTO saved_job (user_id, job_id)
                SELECT %s, je.id FROM job_event je WHERE je.original_url=%s
                ON CONFLICT DO NOTHING;
                """,
                (user_id, job_link),
            )
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            conn.close()
        await q.answer("✅ Job saved!")
        try:
            await q.message.delete()
        except Exception:
            try:
                await q.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
        return

    # SHOW SAVED JOBS
    if data == "act:saved":
        cur.execute(
            """
            SELECT je.title, je.original_url
            FROM saved_job sj
            LEFT JOIN job_event je ON je.id = sj.job_id
            WHERE sj.user_id=%s
            ORDER BY sj.saved_at DESC
            LIMIT 10;
            """,
            (user_id,),
        )
        rows = cur.fetchall()
        conn.close()

        if not rows:
            await q.message.reply_text("Saved list: (empty)")
        else:
            lines = []
            for title, url in rows:
                # Correct, single-line f-string with explicit newline
                lines.append(f"• {title}\n{url}" if url else f"• {title}")
            out = "\n\n".join(lines)
            await q.message.reply_text(f"Saved jobs:\n\n{out}")
        await q.answer()
        return

    # HELP
    if data == "act:help":
        await q.message.reply_text(
            "ℹ️ Use this bot to get job alerts.\n\n"
            "Commands:\n"
            "• /start — show main menu\n"
            "• Search Jobs — type keyword\n"
            "• Save — keep a job\n"
            "• Saved Jobs — view saved list"
        )
        await q.answer()
        return

    # DEBUG
    if data == "act:debug":
        cur.execute('SELECT id, telegram_id FROM "user" WHERE telegram_id=%s;', (tg_id,))
        u = cur.fetchone()
        cur.execute(
            'SELECT COUNT(*) FROM saved_job WHERE user_id=(SELECT id FROM "user" WHERE telegram_id=%s);',
            (tg_id,),
        )
        count = cur.fetchone()[0]
        conn.close()
        await q.message.reply_text(f"🧩 Debug Info:\nInternal user.id: {u[0] if u else None}\nSaved Jobs: {count}")
        await q.answer()
        return

    await q.answer("Unknown action.")
    conn.close()

# ==========================================================
# APP CREATION
# ==========================================================
def build_application():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_keyword))
    app.add_handler(CallbackQueryHandler(handle_search, pattern="act:search"))
    app.add_handler(CallbackQueryHandler(button_callback))
    return app

# ==========================================================
# FASTAPI SERVER
# ==========================================================
fastapi_app = FastAPI()
application = build_application()

@fastapi_app.post(f"/webhook/{WEBHOOK_SECRET}")
async def webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}

@fastapi_app.get("/")
async def root():
    return {"status": "ok"}

def run_uvicorn():
    uvicorn.run("bot:fastapi_app", host="0.0.0.0", port=10000)

if __name__ == "__main__":
    Thread(target=run_uvicorn, daemon=True).start()
    application.run_polling()
