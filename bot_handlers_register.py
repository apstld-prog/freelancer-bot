
from telegram.ext import Application, CommandHandler
from handlers_start import start
from handlers_help import help_command
from handlers_settings import mysettings
from admin_handlers import users_cmd, grant_cmd, block_cmd, unblock_cmd, broadcast_cmd, feedstatus_cmd

def register_handlers(application: Application):
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("mysettings", mysettings))

    # Admin
    application.add_handler(CommandHandler("users", users_cmd))
    application.add_handler(CommandHandler("grant", grant_cmd))
    application.add_handler(CommandHandler("block", block_cmd))
    application.add_handler(CommandHandler("unblock", unblock_cmd))
    application.add_handler(CommandHandler("broadcast", broadcast_cmd))
    application.add_handler(CommandHandler("feedstatus", feedstatus_cmd))
