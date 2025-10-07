# bot.py
# -----------------------------------------
# Telegram bot for Freelancer Alerts
# - Sync SQLAlchemy sessions (SessionLocal), no async get_session
# - Preserves previous menu layout (Keywords | Saved Jobs | Settings | Help | Contact)
# - 10-day trial on /start
# - Admin-only commands appear only to ADMIN_TG_ID in /help
# - /feedsstatus reads stats from feeds_stats.json if present
# - Contact routes user messages to admin with Reply / Decline
# -----------------------------------------

import os
import json
import traceback
from datetime import timedelta

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# --- DB imports (sync) ---
from db import (
    SessionLocal,        # sync session factory
    now_utc,             # returns timezone-aware UTC now
    User,
    Keyword,
    Job,
    SavedJob,
    JobSent,
)

# ------------ Helpers ------------
ADMIN_TG_ID = os.getenv("ADMIN_TG_ID")
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "hook-secret-777")

def db_open():
    """Open a sync SQLAlchemy session."""
    return SessionLocal()

def is_admin(user_id: str | int) -> bool:
    if not ADMIN_TG_ID:
        return False
    try:
        return str(user_id) == str(ADMIN_TG_ID)
    except Exception:
        return False

def safe_markdown(text: str) -> str:
    # minimal escaping for MarkdownV2 / Markdown
    if not text:
        return ""
    return (
        text.replace("_", "\\_")
            .replace("*", "\\*")
            .replace("[", "\\[")
            .replace("`", "\\`")
    )

# --------- UI Layout ----------
def main_menu_kb() -> ReplyKeyboardMarkup:
    # One central panel, two columns, like your earlier layout
    rows = [
        [KeyboardButton("Keywords"), KeyboardButton("Saved Jobs")],
        [KeyboardButton("Settings"), KeyboardButton("Help")],
        [KeyboardButton("Contact")],
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def settings_text(u: User) -> str:
    now = now_utc()
    trial = u.trial_until
    access = u.access_until

    def fmt(dt):
        return dt.strftime("%Y-%m-%d %H:%M UTC") if dt else "—"

    active = (
        (trial and trial >= now) or
        (access and access >= now)
    )

    lines = [
        "*Settings*",
        f"Name: `{u.name or ''}`",
        f"Username: @{u.username}" if u.username else "Username: —",
        f"Started: `{fmt(getattr(u,'started_at',None))}`",
        f"Trial until: `{fmt(trial)}`",
        f"Access until: `{fmt(access)}`",
        f"Status: {'✅ Active' if active else '⛔ Inactive'}",
        "",
        "*Keywords*",
        "• " + "\n• ".join(k.keyword for k in (u.keywords or [])) if (u.keywords) else "No keywords yet.",
        "",
        "_Use the *Keywords* button to add/remove comma-separated keywords (supports Greek too)._",
    ]
    return "\n".join(lines)

def help_text(is_admin_view: bool) -> str:
    base = [
        "*Help*",
        "• Use the main buttons:",
        "  - *Keywords*: add/remove keywords (comma-separated).",
        "  - *Saved Jobs*: view your saved jobs.",
        "  - *Settings*: status, trial, access dates, keywords summary.",
        "  - *Contact*: send a message to the admin (you’ll get a reply here).",
        "",
        "Commands:",
        "• /start – show the main menu and (if new) start a 10-day trial.",
        "• /help – show this help.",
        "• /selftest – send a sample message to verify delivery.",
    ]
    if is_admin_view:
        base += [
            "",
            "*Admin-only*:",
            "• /admin – users & quick actions.",
            "• /grant <telegram_id> <days> – extend access.",
            "• /feedsstatus – last worker cycle feed counts/errors.",
        ]
    return "\n".join(base)

def saved_jobs_message(user_id: int | str) -> tuple[str, InlineKeyboardMarkup | None]:
    db = db_open()
    try:
        u = db.query(User).filter(User.telegram_id == str(user_id)).one_or_none()
        if not u:
            return "No saved jobs.", None
        # fetch recent saved jobs (last 10)
        sj = (
            db.query(SavedJob)
              .filter(SavedJob.user_id == u.id)
              .order_by(SavedJob.created_at.desc())
              .limit(10)
              .all()
        )
        if not sj:
            return "No saved jobs yet.", None

        # Build one text block; for full-window feel, send as one message
        parts = ["*Saved Jobs*"]
        for r in sj:
            j = db.query(Job).filter(Job.id == r.job_id).one_or_none()
            if not j:
                continue
            budget = ""
            if j.budget_min is not None and j.budget_max is not None and j.budget_currency:
                budget = f"{int(j.budget_min)}–{int(j.budget_max)} {j.budget_currency}"
            elif j.budget_min is not None and j.budget_currency:
                budget = f"{int(j.budget_min)}+ {j.budget_currency}"
            title = safe_markdown(j.title or "")
            parts += [
                f"\n*{title}*",
                f"{safe_markdown((j.description or '')[:400])}…",
                f"Budget: `{budget or '—'}`",
                f"Matched: `{j.matched_keyword or '—'}`",
                f"[Original]({j.original_url or j.url})",
                f"[Proposal]({j.proposal_url or j.url})",
            ]
        text = "\n".join(parts)
        # simple inline kb: back to menu
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Back to Menu", callback_data="nav:menu")]
        ])
        return text, kb
    finally:
        db.close()

# -------- Contact flow (user -> admin, admin reply) --------
def admin_reply_kb(sender_tg_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Reply", callback_data=f"admin_reply:{sender_tg_id}"),
         InlineKeyboardButton("Decline", callback_data=f"admin_decline:{sender_tg_id}")]
    ])

async def route_user_message_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not ADMIN_TG_ID:
        await update.message.reply_text("Admin is not configured.")
        return
    u = update.effective_user
    msg = update.message.text or ""
    header = f"✉️ *User Message*\nFrom: `{u.full_name or ''}` (@{u.username or '—'})\nTG ID: `{u.id}`\n\n"
    await context.bot.send_message(
        chat_id=int(ADMIN_TG_ID),
        text=header + safe_markdown(msg),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=admin_reply_kb(str(u.id)),
    )
    await update.message.reply_text("✅ Sent to admin. You’ll get the reply here.")

async def handle_admin_reply_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(update.effective_user.id):
        return
    data = q.data or ""
    if data.startswith("admin_reply:"):
        target = data.split(":", 1)[1]
        context.user_data["reply_target"] = target
        await q.message.reply_text(f"Send your reply to user `{target}` as a normal message now.", parse_mode=ParseMode.MARKDOWN)
    elif data.startswith("admin_decline:"):
        target = data.split(":", 1)[1]
        try:
            await context.bot.send_message(int(target), "❌ Admin declined to respond.")
        except Exception:
            pass
        await q.message.reply_text(f"Declined. (User {target} notified)")

async def admin_sends_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    target = context.user_data.get("reply_target")
    if not target:
        return
    try:
        await context.bot.send_message(int(target), f"🟢 *Admin reply:*\n{safe_markdown(update.message.text or '')}", parse_mode=ParseMode.MARKDOWN)
        await update.message.reply_text("✅ Delivered.")
    except Exception as e:
        await update.message.reply_text(f"Failed to deliver: {e}")

# --------- Commands ----------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u_tg = update.effective_user
    # ensure user in DB + trial
    db = db_open()
    try:
        u = db.query(User).filter(User.telegram_id == str(u_tg.id)).one_or_none()
        if not u:
            u = User(
                telegram_id=str(u_tg.id),
                name=u_tg.full_name or "",
                username=u_tg.username or "",
                started_at=now_utc(),
                created_at=now_utc(),
                updated_at=now_utc(),
                trial_until=now_utc() + timedelta(days=10)
            )
            db.add(u)
            db.commit()
            db.refresh(u)
        else:
            # Fill started_at if missing; keep previous trial
            changed = False
            if not getattr(u, "started_at", None):
                u.started_at = now_utc(); changed = True
            if u.name != (u_tg.full_name or ""):
                u.name = u_tg.full_name or ""; changed = True
            if u.username != (u_tg.username or ""):
                u.username = u_tg.username or ""; changed = True
            if changed:
                u.updated_at = now_utc()
                db.commit()
    finally:
        db.close()

    intro = (
        "*Welcome to Freelancer Alert Bot!*\n"
        "_This bot monitors multiple freelance/job platforms for your keywords and sends you matching listings in real time. "
        "Use the buttons below to manage keywords, view saved jobs, check your status, or contact the admin._"
    )
    await update.message.reply_text(intro, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu_kb())

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_view = is_admin(update.effective_user.id)
    await update.message.reply_text(help_text(admin_view), parse_mode=ParseMode.MARKDOWN)

async def selftest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Self-test OK ✅", reply_markup=main_menu_kb())

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    db = db_open()
    try:
        users = db.query(User).order_by(User.created_at.desc()).limit(30).all()
        lines = ["*Users (latest 30)*"]
        for u in users:
            lines.append(f"• `{u.telegram_id}` @{u.username or '—'}  trial:{'✔' if (u.trial_until and u.trial_until>=now_utc()) else '—'} access:{'✔' if (u.access_until and u.access_until>=now_utc()) else '—'}")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
    finally:
        db.close()

async def grant_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = (context.args or [])
    if len(args) != 2:
        await update.message.reply_text("Usage: /grant <telegram_id> <days>")
        return
    tgt, days = args[0], int(args[1])
    db = db_open()
    try:
        u = db.query(User).filter(User.telegram_id == str(tgt)).one_or_none()
        if not u:
            await update.message.reply_text("User not found.")
            return
        base = u.access_until if (u.access_until and u.access_until > now_utc()) else now_utc()
        u.access_until = base + timedelta(days=days)
        u.updated_at = now_utc()
        db.commit()
        await update.message.reply_text(f"Granted access to {tgt} until {u.access_until.strftime('%Y-%m-%d %H:%M UTC')}")
        try:
            await context.bot.send_message(int(tgt), f"✅ Your access has been extended until {u.access_until.strftime('%Y-%m-%d %H:%M UTC')}.")
        except Exception:
            pass
    finally:
        db.close()

async def feedsstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    # Read stats file if worker published it
    path = os.getenv("FEEDS_STATS_PATH", "feeds_stats.json")
    if not os.path.exists(path):
        await update.message.reply_text("No cycle stats yet.")
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        sent = data.get("sent_this_cycle", 0)
        dur = data.get("cycle_seconds", 0)
        feeds = data.get("feeds_counts", {})
        lines = [f"*Feeds status*\nSent this cycle: `{sent}`  in `{dur:.1f}s`", ""]
        for name, info in feeds.items():
            cnt = info.get("count", 0)
            err = info.get("error")
            lines.append(f"• {name}: `{cnt}`" + (f"  ⚠️ {err}" if err else ""))
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await update.message.reply_text(f"Failed to read stats: {e}")

# --------- Keywords flow (comma-separated, supports Greek) ----------
async def on_text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Route based on button text
    txt = (update.message.text or "").strip()

    if txt.lower() == "keywords":
        await update.message.reply_text(
            "Send your keywords (comma-separated). Example: `led, lighting, λογότυπο`",
            parse_mode=ParseMode.MARKDOWN
        )
        context.user_data["await_keywords"] = True
        return

    if context.user_data.pop("await_keywords", False):
        db = db_open()
        try:
            u = db.query(User).filter(User.telegram_id == str(update.effective_user.id)).one_or_none()
            if not u:
                await update.message.reply_text("Please tap /start first.")
                return
            # parse comma-separated
            raw = txt
            parts = [p.strip() for p in raw.split(",")]
            parts = [p for p in parts if p]
            # de-dup
            seen = set()
            final = []
            for p in parts:
                key = p.lower()
                if key not in seen:
                    seen.add(key)
                    final.append(p)

            # clear + reinsert
            db.query(Keyword).filter(Keyword.user_id == u.id).delete()
            for k in final:
                db.add(Keyword(user_id=u.id, keyword=k, created_at=now_utc()))
            db.commit()
            await update.message.reply_text(f"✅ Saved {len(final)} keywords.", reply_markup=main_menu_kb())
        finally:
            db.close()
        return

    if txt.lower() == "saved jobs":
        text, kb = saved_jobs_message(update.effective_user.id)
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        return

    if txt.lower() == "settings":
        db = db_open()
        try:
            u = db.query(User).filter(User.telegram_id == str(update.effective_user.id)).one_or_none()
            if not u:
                await update.message.reply_text("Please tap /start first.")
                return
            await update.message.reply_text(settings_text(u), parse_mode=ParseMode.MARKDOWN)
        finally:
            db.close()
        return

    if txt.lower() == "help":
        await help_cmd(update, context)
        return

    if txt.lower() == "contact":
        await update.message.reply_text("Contact admin: please send your message here; the admin will reach out.")
        context.user_data["await_contact"] = True
        return

    if context.user_data.pop("await_contact", False):
        # route this message to admin
        await route_user_message_to_admin(update, context)
        return

    # If admin is in reply mode
    if is_admin(update.effective_user.id) and context.user_data.get("reply_target"):
        await admin_sends_reply(update, context)
        return

    # default: ignore unknown text
    await update.message.reply_text("Use the main buttons or /help.", reply_markup=main_menu_kb())

# --------- Callbacks (navigation & admin reply) ----------
async def button_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data or ""
    await q.answer()

    if data == "nav:menu":
        await q.message.reply_text("Main menu:", reply_markup=main_menu_kb())
        return

    # admin reply/decline
    if data.startswith("admin_reply:") or data.startswith("admin_decline:"):
        await handle_admin_reply_click(update, context)
        return

# --------- Error handler ----------
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    tb = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))
    print(f"[PTB ERROR]\n{tb}")
    if ADMIN_TG_ID:
        try:
            await context.bot.send_message(int(ADMIN_TG_ID), f"⚠️ Bot error:\n{tb[:3500]}")
        except Exception:
            pass

# --------- Webhook server ----------
app = FastAPI()

@app.post(f"/webhook/{WEBHOOK_SECRET}")
async def tg_webhook(request: Request):
    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
    except Exception as e:
        print("Webhook error:", e)
        return JSONResponse({"ok": False}, status_code=500)
    return JSONResponse({"ok": True})

@app.get("/")
def root():
    return {"status": "ok"}

# --------- Build application ----------
def build_application():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN missing")
    appb = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands
    appb.add_handler(CommandHandler("start", start_cmd))
    appb.add_handler(CommandHandler("help", help_cmd))
    appb.add_handler(CommandHandler("selftest", selftest_cmd))
    appb.add_handler(CommandHandler("admin", admin_cmd))
    appb.add_handler(CommandHandler("grant", grant_cmd))
    appb.add_handler(CommandHandler("feedsstatus", feedsstatus_cmd))

    # Callbacks
    appb.add_handler(CallbackQueryHandler(button_cb))

    # Text router (buttons + flows)
    appb.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text_router))

    # Errors
    appb.add_error_handler(on_error)

    return appb

# Create PTB app (global for webhook handler)
application = build_application()

# Set webhook at startup
async def on_startup():
    if WEBHOOK_URL:
        await application.bot.delete_webhook()
        await application.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook/{WEBHOOK_SECRET}")
        print(f"Webhook set to {WEBHOOK_URL}/webhook/{WEBHOOK_SECRET}")

if __name__ == "__main__":
    # PTB startup tasks
    application.run_webhook = on_startup  # keep ref to avoid lint warnings
    # Start the ASGI app
    uvicorn.run("bot:app", host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
