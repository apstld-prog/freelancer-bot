import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from db_keywords import get_keywords, add_keywords, delete_keyword

log = logging.getLogger("handlers_settings")


async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    kws = get_keywords(uid)
    if not kws:
        kws_text = "(none)"
    else:
        kws_text = ", ".join(kws)

    text = (
        "*Settings*\n"
        "______________________________\n"
        "*Keywords:*\n"
        f"{kws_text}\n\n"
        "Add or remove keywords below."
    )

    kb = [
        [InlineKeyboardButton("Ã¢Å¾â€¢ Add Keyword", callback_data="ui:add_kw")],
        [InlineKeyboardButton("Ã¢Å¾â€“ Delete Keyword", callback_data="ui:del_kw")],
        [InlineKeyboardButton("Ã¢Â¬â€¦ Back", callback_data="ui:back_home")],
    ]

    await update.message.reply_text(
        text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb)
    )


async def add_keyword_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        "Send the keyword you want to add:"
    )
    context.user_data["awaiting_kw_add"] = True


async def delete_keyword_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        "Send the keyword you want to delete:"
    )
    context.user_data["awaiting_kw_delete"] = True


async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()

    # Add keyword
    if context.user_data.get("awaiting_kw_add"):
        add_keywords(uid, [text])
        await update.message.reply_text(f"Ã¢Å“â€¦ Added keyword: *{text}*", parse_mode="Markdown")
        context.user_data["awaiting_kw_add"] = False
        return

    # Delete keyword
    if context.user_data.get("awaiting_kw_delete"):
        delete_keyword(uid, text)
        await update.message.reply_text(f"Ã°Å¸â€”â€˜Ã¯Â¸Â Deleted keyword: *{text}*", parse_mode="Markdown")
        context.user_data["awaiting_kw_delete"] = False
        return


