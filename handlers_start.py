
from telegram import Update
from telegram.ext import ContextTypes
from ui_keyboards import main_menu_kb
from ui_texts import welcome_full, features_block
from config import ADMIN_IDS, TRIAL_DAYS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_admin = update.effective_user.id in ADMIN_IDS
    await update.effective_chat.send_message(
        welcome_full(trial_days=TRIAL_DAYS), parse_mode="HTML", reply_markup=main_menu_kb(is_admin=is_admin)
    )
    await update.effective_chat.send_message(features_block(), parse_mode="HTML")
