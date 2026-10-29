from telegram import Update
from telegram.ext import ContextTypes
from database.job_repo import job_repo

async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    records = job_repo.get_user_history(update.effective_user.id)
    if not records:
        await update.message.reply_text("📜 No downloads recorded yet.")
        return
    lines = ["📜 **Your Downloads:**\n"]
    for i, r in enumerate(records, 1):
        lines.append(f"{i}. {r.get('title')} ({r.get('selected_quality')}) - {r.get('credits_spent')} Cr")
    await update.message.reply_text("\n".join(lines))