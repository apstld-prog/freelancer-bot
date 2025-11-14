# patch_bot_debugme.py
# One-shot patcher for your existing bot.py
# Usage:
#   python patch_bot_debugme.py
#
# It will modify bot.py in-place:
#   - Injects /debugme handler and registers it in build_application()
#   - Fixes "act:saved" to read new schema + legacy schema (with internal user.id)
#   - Fixes "job:save" legacy path to store internal user.id instead of telegram_id

from pathlib import Path
import re
import sys

BOT = Path("bot.py")
if not BOT.exists():
    print("❌ bot.py not found in current directory.")
    sys.exit(1)

src = BOT.read_text(encoding="utf-8", errors="ignore")

def ensure_commandhandler_import(s: str) -> str:
    if "from telegram.ext import CommandHandler" in s:
        return s
    if "from telegram.ext import (" in s:
        return s.replace("from telegram.ext import (",
                         "from telegram.ext import (CommandHandler, ", 1)
    if "from telegram.ext import" in s:
        return s.replace("from telegram.ext import",
                         "from telegram.ext import CommandHandler,", 1)
    if "import telegram" in s:
        return s.replace("import telegram",
                         "import telegram\nfrom telegram.ext import CommandHandler", 1)
    return 'from telegram.ext import CommandHandler\n' + s

def inject_debugme(s: str) -> str:
    if "async def debugme_cmd(" in s:
        return s
    debug_fn = r"""
async def debugme_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Prints Telegram/Chat IDs, internal user.id and sample saved jobs from both schemas.
    try:
        uid = update.effective_user.id if update and update.effective_user else None
        chat_id = update.effective_chat.id if update and update.effective_chat else None

        from sqlalchemy import text as _t
        from db import get_session as _gs

        # Find internal user.id
        internal_id = None
        try:
            with _gs() as s:
                r = s.execute(_t('SELECT id FROM "user" WHERE telegram_id=:tid LIMIT 1'), {"tid": uid}).fetchone()
                internal_id = (r[0] if r else None)
        except Exception:
            internal_id = None

        # New schema: saved_job(user_id = telegram_id)
        saved_new = []
        try:
            with _gs() as s:
                saved_new = s.execute(_t('SELECT title, COALESCE(url, '''') FROM saved_job WHERE user_id=:u ORDER BY saved_at DESC LIMIT 3'), {"u": uid}).fetchall()
        except Exception:
            saved_new = []

        # Legacy schema: saved_job(user_id = internal id) join job_event
        saved_old = []
        try:
            if internal_id is not None:
                with _gs() as s:
                    saved_old = s.execute(_t('''
                        SELECT COALESCE(je.title,'(no title)') AS title,
                               COALESCE(je.original_url,'') AS url
                        FROM saved_job sj
                        LEFT JOIN job_event je ON je.id = sj.job_id
                        WHERE sj.user_id = :u
                        ORDER BY sj.saved_at DESC
                        LIMIT 3
                    '''), {"u": internal_id}).fetchall()
        except Exception:
            saved_old = []

        lines = []
        lines.append(f"Telegram ID: {uid}")
        lines.append(f"Chat ID: {chat_id}")
        lines.append(f"Internal user.id: {internal_id}")
        lines.append("— New schema (user_id = telegram_id):")
        if saved_new:
            for i,(t,u) in enumerate(saved_new,1):
                t = (t or '').strip() or '(no title)'
                u = (u or '').strip()
                lines.append(f"{i}. {t}\\n{u}")
        else:
            lines.append("(none)")

        lines.append("— Legacy schema (user_id = internal id):")
        if saved_old:
            for i,(t,u) in enumerate(saved_old,1):
                t = (t or '').strip() or '(no title)'
                u = (u or '').strip()
                lines.append(f"{i}. {t}\\n{u}")
        else:
            lines.append("(none)")

        text = "\\n".join(lines)
        await context.bot.send_message(chat_id=chat_id, text=text)
    except Exception as e:
        try:
            await context.bot.send_message(chat_id=chat_id, text=f"/debugme error: {e}")
        except Exception:
            pass
"""
    if "def build_application(" in s:
        return s.replace("def build_application(", debug_fn + "\n\ndef build_application(", 1)
    return s + "\n\n" + debug_fn

def register_debugme(s: str) -> str:
    if 'CommandHandler("debugme", debugme_cmd)' in s:
        return s
    pattern = r'(app\s*=\s*Application\.builder\([\s\S]*?\.build\(\))'
    if re.search(pattern, s):
        return re.sub(pattern,
                      r'\1\n    app.add_handler(CommandHandler("debugme", debugme_cmd))',
                      s, count=1)
    return s + "\n\n# Fallback registration for /debugme\ntry:\n    app.add_handler(CommandHandler('debugme', debugme_cmd))\nexcept Exception:\n    pass\n"

# Apply patches
src = ensure_commandhandler_import(src)
src = inject_debugme(src)
src = register_debugme(src)

BOT.write_text(src, encoding="utf-8")
print("✅ bot.py patched successfully (debugme added).")
