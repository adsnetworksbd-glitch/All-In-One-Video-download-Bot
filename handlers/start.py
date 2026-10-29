from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from database.user_repo import UserRepository
from database.credit_repo import CreditRepository

user_repo = UserRepository()
credit_repo = CreditRepository()

MAIN_MENU = ReplyKeyboardMarkup([
    [KeyboardButton("📥 Download Categories"), KeyboardButton("🔍 Search")],
    [KeyboardButton("📜 My History"), KeyboardButton("⚙️ Settings")],
    [KeyboardButton("📊 My Statistics"), KeyboardButton("💬 Support")]
], resize_keyboard=True, is_persistent=True)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ref_by = None
    if context.args and context.args[0].startswith("ref_"):
        try: ref_by = int(context.args[0].replace("ref_", ""))
        except: pass

    u, is_new = user_repo.onboard_user_if_new(user.id, user.first_name, user.username, user.last_name, ref_by)
    if is_new and ref_by:
        credit_repo.add_reward_credits(ref_by, 20, "REFERRAL_REWARD", f"ref_{user.id}", "Referral bonus")
        credit_repo.add_reward_credits(user.id, 10, "REFERRAL_REWARD", f"ref_by_{ref_by}", "Joining bonus")

    bal = u.get('credit_balance', 50)
    await update.message.reply_text(
        f"👋 **Welcome, {user.first_name}!**\n\n🎬 **All-in-One Video Downloader Bot**\n💰 Balance: `{bal}` Credits\n\nSend any video link to begin!",
        parse_mode="Markdown", reply_markup=MAIN_MENU
    )