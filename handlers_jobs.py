
from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from ui_keyboards import job_action_kb

async def send_job_card(bot, chat_id: int, text: str, proposal_url: str, original_url: str):
    kb = job_action_kb(proposal_url, original_url)
    await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=kb)
