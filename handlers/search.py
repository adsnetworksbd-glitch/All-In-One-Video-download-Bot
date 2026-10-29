from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from database.category_repo import category_repo

async def prompt_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["awaiting_search"] = True
    await update.message.reply_text("🔍 Type platform name to search (e.g. YouTube, TikTok):")

async def handle_search_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_search"): return
    context.user_data["awaiting_search"] = False
    res = category_repo.search_categories(update.message.text.strip())
    if not res:
        await update.message.reply_text("❌ No platform found.")
        return
    btns = [[InlineKeyboardButton(f"{c.get('icon','📁')} {c['name']}", callback_data=f"cat_select:{c['slug']}")] for c in res]
    await update.message.reply_text("🎯 **Matching Platforms:**", reply_markup=InlineKeyboardMarkup(btns))