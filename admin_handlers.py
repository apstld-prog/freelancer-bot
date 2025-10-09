
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes
from sqlalchemy import func
from config import ADMIN_IDS, STATS_WINDOW_HOURS
from db import SessionLocal, User
from db_events import get_platform_stats

def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return
    with SessionLocal() as s:
        rows = s.query(User).order_by(User.id.desc()).limit(100).all()
        lines = ["<b>Users</b>"]
        for u in rows:
            kw_count = len(u.keywords or [])
            trial = getattr(u, "trial_end", None)
            lic = getattr(u, "license_until", None)
            active = "✅" if u.is_active else "❌"
            blocked = "✅" if u.is_blocked else "❌"
            lines.append(f"• <a href="tg://user?id={u.telegram_id}">{u.telegram_id}</a> — kw:{kw_count} | trial:{trial} | lic:{lic} | A:{active} B:{blocked}")
        await update.effective_chat.send_message("\n".join(lines), parse_mode="HTML")

async def grant_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return
    if len(context.args) < 2:
        await update.effective_chat.send_message("Usage: /grant <telegram_id> <days>")
        return
    tg_id = int(context.args[0]); days = int(context.args[1])
    until = datetime.utcnow() + timedelta(days=days)
    with SessionLocal() as s:
        u = s.query(User).filter(User.telegram_id == tg_id).first()
        if not u:
            await update.effective_chat.send_message("User not found.")
            return
        u.license_until = until
        s.commit()
    await update.effective_chat.send_message(f"✅ Granted license to {tg_id} until {until.isoformat()}")

async def block_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.effective_chat.send_message("Usage: /block <telegram_id>")
        return
    tg_id = int(context.args[0])
    with SessionLocal() as s:
        u = s.query(User).filter(User.telegram_id == tg_id).first()
        if not u:
            await update.effective_chat.send_message("User not found.")
            return
        u.is_blocked = True
        s.commit()
    await update.effective_chat.send_message(f"⛔ Blocked {tg_id}")

async def unblock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.effective_chat.send_message("Usage: /unblock <telegram_id>")
        return
    tg_id = int(context.args[0])
    with SessionLocal() as s:
        u = s.query(User).filter(User.telegram_id == tg_id).first()
        if not u:
            await update.effective_chat.send_message("User not found.")
            return
        u.is_blocked = False
        s.commit()
    await update.effective_chat.send_message(f"✅ Unblocked {tg_id}")

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.effective_chat.send_message("Usage: /broadcast <text>")
        return
    text = " ".join(context.args)
    # You probably have a list of active users in DB; we filter by is_active and not blocked
    with SessionLocal() as s:
        users = s.query(User).filter(User.is_active == True, User.is_blocked == False).all()
    sent = 0
    for u in users:
        try:
            await context.bot.send_message(chat_id=u.telegram_id, text=text, parse_mode="HTML")
            sent += 1
        except Exception:
            pass
    await update.effective_chat.send_message(f"📣 Broadcast sent to {sent} users.")

async def feedstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return
    hours = STATS_WINDOW_HOURS
    stats = get_platform_stats(hours)
    if not stats:
        await update.effective_chat.send_message(f"No events in last {hours}h.")
        return
    lines = [f"📊 Feed status (last {hours}h):"]
    for src, cnt in stats.items():
        lines.append(f"• {src}: {cnt}")
    await update.effective_chat.send_message("\n".join(lines))
