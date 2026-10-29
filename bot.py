from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from config import get_settings
from database.firebase import firebase_manager
from services.job_queue import job_recovery_manager

from handlers.start import start_command
from handlers.categories import show_categories, category_callback_handler
from handlers.search import prompt_search, handle_search_query
from handlers.downloads import handle_video_url_message, download_quality_callback
from handlers.history import show_history
from handlers.settings import show_settings
from handlers.referrals import show_referrals
from handlers.support import show_statistics, show_support

async def main_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text
    if t == "📥 Download Categories": await show_categories(update, context)
    elif t == "🔍 Search": await prompt_search(update, context)
    elif t == "📜 My History": await show_history(update, context)
    elif t == "⚙️ Settings": await show_settings(update, context)
    elif t == "📊 My Statistics": await show_statistics(update, context)
    elif t == "💬 Support": await show_support(update, context)
    elif context.user_data.get("awaiting_search"): await handle_search_query(update, context)
    elif t.startswith("http"): await handle_video_url_message(update, context)

def main():
    settings = get_settings()
    firebase_manager.initialize()
    job_recovery_manager.reconcile_stranded_jobs()

    app = ApplicationBuilder().token(settings.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(category_callback_handler, pattern="^cat_"))
    app.add_handler(CallbackQueryHandler(download_quality_callback, pattern="^dl_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, main_router))

    print("Bot polling started...")
    app.run_polling()

if __name__ == "__main__":
    main()