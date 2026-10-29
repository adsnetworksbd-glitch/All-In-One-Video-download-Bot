from telegram import Update
from telegram.ext import ContextTypes
from database.user_repo import UserRepository

user_repo = UserRepository()
async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = user_repo.get_user(update.effective_user.id) or {}
    await update.message.reply_text(f"⚙️ **Settings**\nID: `{update.effective_user.id}`\nBalance: `{u.get('credit_balance', 0)}` Credits", parse_mode="Markdown")