import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from utils import get_user, get_keywords, get_countries, get_proposal_template
from db_keywords import delete_keyword
from db_events import fetch_saved_jobs

log = logging.getLogger("handlers_ui")


# ======================
#  SHARED UI BUILDERS
# ======================

def build_settings_message(user):
    kw = ", ".join(get_keywords(user.id)) or "(none)"
    countries = ", ".join(get_countries(user.id)) or "ALL"
    proposal = get_proposal_template(user.id) or "(none)"

    return (
        "🛠 *Your Settings*\n"
        f"• *Keywords:* {kw}\n"
        f"• *Countries:* {countries}\n"
        f"• *Proposal template:* {proposal}\n"
        f"🟢 *Start date:* {user.created_at}\n"
        f"🟢 *Trial ends:* {user.trial_until}\n"
        f"🟢 *License until:* {user.license_until}\n"
        f"✅ *Active:* {'☑️' if user.is_active else '❌'}\n"
        f"🚫 *Blocked:* {'☑️' if user.is_blocked else '❌'}\n"
        "________________________________________\n"
        "🌍 *Platforms monitored:*\n"
        "Global: Freelancer.com, PeoplePerHour, Malt, Workana, Guru, 99designs,\n"
        "Toptal*, Codeable*, YunoJuno*, Worksome*, twago, freelancermap\n"
        "(*referral/curated platforms)\n"
        "Greece: JobFind.gr, Skywalker.gr, Kariera.gr\n"
        "________________________________________\n"
        "For extension, contact the admin."
    )


def build_settings_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add keyword", callback_data="act:addkw")],
        [InlineKeyboardButton("➖ Remove keyword", callback_data="act:delkw")],
        [InlineKeyboardButton("🌍 Set countries", callback_data="act:setcountries")],
        [InlineKeyboardButton("📄 Set proposal template", callback_data="act:setproposal")],
        [InlineKeyboardButton("⬅️ Back", callback_data="ui:main")],
    ])


def build_saved_jobs_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back", callback_data="ui:main")]
    ])


def build_help_message():
    return (
        "🩵 *Help / How it works*\n"
        "1️⃣ Add keywords with `/addkeyword python, telegram` (comma-separated).\n"
        "2️⃣ Set your countries with `/setcountry US,UK` or `ALL`.\n"
        "3️⃣ Save proposal template with `/setproposal <text>`.\n"
        " Placeholders: {jobtitle}, {experience}, {stack}, {availability},\n"
        " {step1}, {step2}, {step3}, {budgettime}, {portfolio}, {name}\n"
        "4️⃣ When a job arrives you can:\n"
        " ⭐ *Keep*\n"
        " 🗑️ *Delete*\n"
        " 📩 *Proposal* → affiliate job link\n"
        " 🌐 *Original* → direct affiliate link\n"
        "➡️ `/mysettings` anytime.\n"
        "➡️ `/selftest` for a test job.\n"
        "➡️ `/platforms CC` (e.g. `/platforms GR`).\n"
        "________________________________________\n"
        "🌍 Platforms monitored:\n"
        "Freelancer.com, PeoplePerHour, Malt, Workana, Guru,\n"
        "99designs, Toptal*, Codeable*, YunoJuno*, Worksome*,\n"
        "twago, freelancermap\n"
        "Greece: JobFind.gr, Skywalker.gr, Kariera.gr"
    )


def build_contact_message(user):
    return (
        "📩 *Contact the Admin*\n"
        "Send your message here and the admin will receive it.\n"
        "You will get a reply directly inside this chat.\n"
        "________________________________________\n"
        f"*Your ID:* `{user.telegram_id}`"
    )


def build_admin_message():
    return (
        "👑 *Admin commands*\n"
        "• `/users` – list users\n"
        "• `/grant <telegram_id> <days>` – extend license\n"
        "• `/block <telegram_id>` / `/unblock <telegram_id>`\n"
        "• `/broadcast <text>` – send to all active users\n"
        "• `/feedsstatus` – show feed toggles\n"
        "/SELFTEST  \n"
        "/WORKERS TEST"
    )


def main_menu_keyboard(is_admin):
    rows = [
        [
            InlineKeyboardButton("🟩 Keywords", callback_data="ui:keywords"),
            InlineKeyboardButton("⚙️ Settings", callback_data="ui:settings"),
        ],
        [
            InlineKeyboardButton("📘 Help", callback_data="ui:help"),
            InlineKeyboardButton("💾 Saved", callback_data="ui:saved"),
        ],
        [InlineKeyboardButton("📞 Contact", callback_data="ui:contact")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton("🔥 Admin", callback_data="ui:admin")])
    return InlineKeyboardMarkup(rows)


# ======================
#  MAIN UI ROUTER
# ======================

async def handle_ui_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Central router for UI screens."""
    try:
        query = update.callback_query
        await query.answer()

        data = query.data  # e.g. ui:settings
        tid = query.from_user.id

        user = get_user(tid)

        # Check admin
        admin_ids = context.bot_data.get("ADMIN_IDS", [])
        is_admin = tid in admin_ids if admin_ids else False

        # ========== MAIN ==========
        if data == "ui:main":
            await query.edit_message_text(
                "👋 *Welcome back!*",
                reply_markup=main_menu_keyboard(is_admin),
                parse_mode="Markdown"
            )
            return

        # ========== SETTINGS ==========
        if data == "ui:settings":
            await query.edit_message_text(
                build_settings_message(user),
                reply_markup=build_settings_keyboard(),
                parse_mode="Markdown"
            )
            return

        # ========== KEYWORDS ==========
        if data == "ui:keywords":
            kws = ", ".join(get_keywords(user.id)) or "(none)"
            await query.edit_message_text(
                f"🟩 *Your Keywords*\n{kws}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ Add", callback_data="act:addkw")],
                    [InlineKeyboardButton("➖ Remove", callback_data="act:delkw")],
                    [InlineKeyboardButton("⬅️ Back", callback_data="ui:main")],
                ]),
                parse_mode="Markdown"
            )
            return

        # ========== SAVED ==========
        if data == "ui:saved":
            saved = fetch_saved_jobs(user.id)
            if not saved:
                msg = "💾 *Saved Jobs*\nYou have no saved jobs."
            else:
                msg = "💾 *Saved Jobs*\n" + "\n".join(
                    f"- {j.title} ({j.platform})" for j in saved
                )

            await query.edit_message_text(
                msg,
                reply_markup=build_saved_jobs_keyboard(),
                parse_mode="Markdown"
            )
            return

        # ========== HELP ==========
        if data == "ui:help":
            await query.edit_message_text(
                build_help_message(),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Back", callback_data="ui:main")]
                ]),
                parse_mode="Markdown"
            )
            return

        # ========== CONTACT ==========
        if data == "ui:contact":
            await query.edit_message_text(
                build_contact_message(user),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Back", callback_data="ui:main")]
                ]),
                parse_mode="Markdown"
            )
            return

        # ========== ADMIN ==========
        if data == "ui:admin" and is_admin:
            await query.edit_message_text(
                build_admin_message(),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Back", callback_data="ui:main")]
                ]),
                parse_mode="Markdown"
            )
            return

    except Exception as e:
        log.error(f"UI callback error: {e}", exc_info=True)
        try:
            await update.callback_query.answer("Error", show_alert=True)
        except:
            pass


# ==================================
#  FREE-TEXT USER MESSAGES (Contact)
# ==================================

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles free messages (used for Contact → Admin inbox)."""
    try:
        tid = update.effective_user.id
        user = get_user(tid)

        # Forward to admin
        admin_ids = context.bot_data.get("ADMIN_IDS", [])
        if not admin_ids:
            await update.message.reply_text("Admin not configured.")
            return

        for admin in admin_ids:
            await context.bot.send_message(
                chat_id=admin,
                text=(
                    "📩 *New message from user*\n"
                    f"ID: `{tid}`\n"
                    f"{update.message.text}\n"
                    "________________________________________\n"
                    "🕒 Sent just now"
                ),
                parse_mode="Markdown"
            )

        await update.message.reply_text("✅ Message sent to admin.")

    except Exception as e:
        log.error(f"Message handler error: {e}", exc_info=True)

