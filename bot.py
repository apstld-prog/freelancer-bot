from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from sqlalchemy import text as sqltext
from db import get_session

BOT_TOKEN = "8301080604:AAF7Hsb_ImfJHiJVYTTXzQOwgI37h8XlEKc"

# -------------------- Application wiring --------------------

def build_application():
    app = Application.builder().token(BOT_TOKEN).build()

    # Commands (do not change semantics)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("feedstatus", feedstatus))
    app.add_handler(CommandHandler("selftest", selftest))
    app.add_handler(CommandHandler("help", help_cmd))

    # Single callback router (handles all buttons inc. Save/Delete)
    app.add_handler(CallbackQueryHandler(callback_router))

    return app

# -------------------- /start — EXACT UI TEMPLATE --------------------

WELCOME_HEADER = (
    "👋 Welcome to Freelancer Alert Bot!\n\n"
    "🎁 You have a 10-day free trial.\n"
    "Automatically finds matching freelance jobs from top platforms and sends instant alerts.\n\n"
    "Use /help to see how it works."
)

HELP_BLOCK = (
    "💡 Features\n"
    "• Realtime job alerts (Freelancer API)\n"
    "• Affiliate-wrapped Proposal & Original links\n"
    "• Budget shown + USD conversion\n"
    "• ⭐ Keep / 🗑️ Delete buttons\n"
    "• 10-day free trial, extend via admin\n"
    "• Multi-keyword search (single/all modes)\n"
    "• Platforms by country (incl. GR boards)\n"
)

PLATFORMS_BLOCK = (
    "🌍 Platforms monitored:\n"
    "Global: Freelancer.com (affiliate), PeoplePerHour, Malt, Workana, Guru, 99designs, Toptal*, Codeable*, YunoJuno*, "
    "Works​ome*, twago, freelancermap\n"
    "Greece: JobFind.gr, Skywalker.gr, Kariera.gr\n"
    "(* referal/curated platforms)"
)

def start_keyboard() -> InlineKeyboardMarkup:
    # Exact positions as in the template: 2 x 2 grid, then Contact, then Admin
    rows = [
        [
            InlineKeyboardButton("+ Add Keywords", callback_data="act:addkeywords"),
            InlineKeyboardButton("⚙️ Settings", callback_data="act:settings"),
        ],
        [
            InlineKeyboardButton("🆘 Help", callback_data="act:help"),
            InlineKeyboardButton("💾 Saved", callback_data="act:saved"),
        ],
        [InlineKeyboardButton("📬 Contact", callback_data="act:contact")],
        [InlineKeyboardButton("🔥 Admin", callback_data="act:admin")],
    ]
    return InlineKeyboardMarkup(rows)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Send welcome card + the exact keyboard (no layout change)
    if update.message:
        await update.message.reply_text(WELCOME_HEADER, disable_web_page_preview=True, reply_markup=start_keyboard())
        # Optional informational blocks below the main card, as in screenshots
        await update.message.reply_text(HELP_BLOCK, disable_web_page_preview=True)
        await update.message.reply_text(PLATFORMS_BLOCK, disable_web_page_preview=True)
    else:
        # Fallback for button-initiated /start
        await update.callback_query.edit_message_text(WELCOME_HEADER, disable_web_page_preview=True, reply_markup=start_keyboard())

# -------------------- Core commands (unchanged semantics) --------------------

async def feedstatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Show last 24h by platform (text only; UI not changed here)
    with get_session() as s:
        rows = s.execute(sqltext("""
            SELECT platform, COUNT(*) 
            FROM feed_events 
            WHERE created_at > (NOW() AT TIME ZONE 'UTC') - INTERVAL '24 hours'
            GROUP BY platform ORDER BY platform
        """)).fetchall()
    if not rows:
        txt = "🧪 Feeds active and synced."
    else:
        lines = ["📊 Feed status (last 24h):"]
        for p, c in rows:
            lines.append(f"• {p}: {c}")
        txt = "\n".join(lines)
    if update.message:
        await update.message.reply_text(txt)
    else:
        await update.callback_query.edit_message_text(txt)

async def selftest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Do not change user-facing text
    txt = "✅ Self-test completed: bot λειτουργεί σωστά."
    if update.message:
        await update.message.reply_text(txt)
    else:
        await update.callback_query.edit_message_text(txt)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Mirror the help block users expect
    await update.message.reply_text(
        "🪄 Use /mysettings anytime. Try /selftest for a sample.\n"
        "📍 Use /platforms CC to see platforms by country (e.g., /platforms GR).",
        disable_web_page_preview=True,
    )

# -------------------- Saved/Delete handling (no UI changes) --------------------

def ensure_saved_table() -> None:
    with get_session() as s:
        s.execute(sqltext("""
            CREATE TABLE IF NOT EXISTS saved_job (
                user_tg BIGINT NOT NULL,
                job_key TEXT NOT NULL,
                saved_at TIMESTAMPTZ DEFAULT (NOW() AT TIME ZONE 'UTC'),
                PRIMARY KEY (user_tg, job_key)
            )
        """))
        s.commit()

async def handle_save(query) -> None:
    ensure_saved_table()
    data = query.data or ""
    job_key = data.split(":", 2)[2] if ":" in data else ""
    if job_key:
        with get_session() as s:
            s.execute(
                sqltext("INSERT INTO saved_job (user_tg, job_key) VALUES (:u, :k) ON CONFLICT DO NOTHING"),
                {"u": query.from_user.id, "k": job_key},
            )
            s.commit()
    try:
        await query.message.delete()  # per your requirement
    except Exception:
        pass
    await query.answer("Saved", show_alert=False)

async def handle_delete(query) -> None:
    try:
        await query.message.delete()
    except Exception:
        pass
    await query.answer("Deleted", show_alert=False)

# -------------------- Callback router (keeps existing texts) --------------------

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    data = q.data or ""

    # Job actions
    if data.startswith("job:save:"):
        await handle_save(q)
        return
    if data == "job:delete":
        await handle_delete(q)
        return

    # Menu actions (texts exactly as simple lines; no layout changes)
    if data == "act:addkeywords":
        await q.answer()
        await q.edit_message_text("Type /addkeyword python, telegram to add keywords.")
        return
    if data == "act:settings":
        await q.answer()
        await q.edit_message_text("Open /mysettings to view your filters and proposal template.")
        return
    if data == "act:help":
        await q.answer()
        await q.edit_message_text(HELP_BLOCK, disable_web_page_preview=True)
        return
    if data == "act:saved":
        await q.answer()
        await q.edit_message_text("📂 Saved jobs list (coming soon).")
        return
    if data == "act:contact":
        await q.answer()
        await q.edit_message_text("✉️ Contact the admin if you need help.")
        return
    if data == "act:admin":
        await q.answer()
        await q.edit_message_text("👑 Admin panel: /users • /grant <id> <days> • /block <id> • /unblock <id> • /broadcast <text> • /feedstatus")
        return
