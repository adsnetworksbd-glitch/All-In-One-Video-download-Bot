
import os
from aiohttp import web

async def health_check(request):
    return web.Response(text="Bot is running and healthy!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Health check web server bound to port {port}")


import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters
from config import get_settings
from database.firebase import firebase_manager
from logger import logger
from services.broadcast_worker import BroadcastWorker
from services.credit_adjustment_worker import CreditAdjustmentWorker
from services.job_queue import job_recovery_manager
from services.provider_test_worker import ProviderTestWorker
from handlers.categories import category_callback_handler, show_categories
from handlers.downloads import download_quality_callback, handle_video_url_message
from handlers.history import show_history
from handlers.referrals import show_referrals
from handlers.search import handle_search_query, prompt_search
from handlers.settings import show_settings
from handlers.start import start_command
from handlers.support import show_statistics, show_support

async def main_menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    text = update.message.text.strip()
    try:
        if firebase_manager.safe_get("bot_settings/maintenance_mode") is True and text.startswith("http"):
            await update.message.reply_text("🚧 **Maintenance Mode:** Video downloads are temporarily paused. Please check back shortly.")
            return
    except Exception: pass

    if text == "📥 Download Categories": await show_categories(update, context)
    elif text == "🔍 Search": await prompt_search(update, context)
    elif text == "📜 My History": await show_history(update, context)
    elif text == "⚙️ Settings": await show_settings(update, context)
    elif text == "📊 My Statistics": await show_statistics(update, context)
    elif text == "💬 Support": await show_support(update, context)
    elif context.user_data.get("awaiting_search"): await handle_search_query(update, context)
    elif text.startswith("http"): await handle_video_url_message(update, context)

async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Global exception: {context.error}", exc_info=context.error)

async def post_init(app):
    job_recovery_manager.reconcile_stranded_jobs()
    asyncio.create_task(BroadcastWorker(app).start())
    asyncio.create_task(ProviderTestWorker().start())
    asyncio.create_task(CreditAdjustmentWorker().start())
    logger.info("Background workers started successfully.")

def main():
    settings = get_settings()
    firebase_manager.initialize()
    app = ApplicationBuilder().token(settings.TELEGRAM_BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(category_callback_handler, pattern="^cat_"))
    app.add_handler(CallbackQueryHandler(download_quality_callback, pattern="^dl_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu_router))
    app.add_error_handler(global_error_handler)
    logger.info("Bot is polling updates...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()