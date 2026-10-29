from telegram import Update
from telegram.ext import ContextTypes
from database.user_repo import UserRepository
from database.job_repo import job_repo

user_repo = UserRepository()
async def show_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = user_repo.get_user(update.effective_user.id) or {}
    h = job_repo.get_user_history(update.effective_user.id, limit=50)
    spent = sum(x.get("credits_spent", 0) for x in h)
    await update.message.reply_text(f"📊 **Statistics**\nDownloads: `{len(h)}`\nSpent: `{spent}` Credits\nBalance: `{u.get('credit_balance', 0)}` Credits", parse_mode="Markdown")

async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💬 **Support:** Contact @admin for assistance.")