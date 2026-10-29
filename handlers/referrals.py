from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from config import get_settings

async def show_referrals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    b = get_settings().BOT_USERNAME
    link = f"https://t.me/{b}?start=ref_{update.effective_user.id}"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("📤 Share Link", url=f"https://t.me/share/url?url={link}")]])
    await update.message.reply_text(f"🤝 **Invite Friends & Earn Credits!**\n\nLink:\n`{link}`", parse_mode="Markdown", reply_markup=markup)