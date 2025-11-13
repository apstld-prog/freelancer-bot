import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters
from db_keywords import get_keywords, add_keywords, delete_keyword

log = logging.getLogger("handlers_settings")


async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    kws = get_keywords(uid)
    kws_text = ", ".join(kws) if kws else "(none)"

    text = (
        "*Settings*\n"
        "______________________________\n"
        "*Keywords:*\n"
        f"{kws_text}\n\n"
        "Add or remove keywords below."
    )

    kb = [
        [InlineKeyboardButton("➕ Add Keyword", callback_data="ui:add_kw")],
        [InlineKeyboardButton("➖ Delete Keyword", callback_data="ui:del_kw")],
        [InlineKeyboardButton("⬅ Back", callback_data="ui:back_home")],
    ]

    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def add_keyword_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("Send the keyword you want to add:")
    context.user_data["awaiting_kw_add"] = True


async def delete_keyword_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("Send the keyword you want to delete:")
    context.user_data["awaiting_kw_delete"] = True


async def settings_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()

    if context.user_data.get("awaiting_kw_add"):
        add_keywords(uid, [text])
        await update.message.reply_text(f"✔ Added keyword: *{text}*", parse_mode="Markdown")
        context.user_data["awaiting_kw_add"] = False
        return

    if context.user_data.get("awaiting_kw_delete"):
        delete_keyword(uid, text)
        await update.message.reply_text(f"🗑️ Deleted keyword: *{text}*", parse_mode="Markdown")
        context.user_data["awaiting_kw_delete"] = False
        return


def register_settings_handlers(app):
    app.add_handler(CallbackQueryHandler(add_keyword_prompt, pattern="^ui:add_kw$"))
    app.add_handler(CallbackQueryHandler(delete_keyword_prompt, pattern="^ui:del_kw$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, settings_message_handler))
