from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from services.download_service import download_service, get_credit_price
from database.user_repo import UserRepository

user_repo = UserRepository()
CACHE = {}

async def handle_video_url_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user = update.effective_user
    if user_repo.is_user_banned(user.id):
        await update.message.reply_text("⛔ Account suspended.")
        return

    msg = await update.message.reply_text("🔎 Analyzing video...")
    try:
        j_id, meta = await download_service.prepare_video_options(text, user.id)
        CACHE[j_id] = {"meta": meta, "url": text, "plat": meta.platform}
        kb = [[InlineKeyboardButton(f"🎬 {f.label} ({get_credit_price(f.format_id)} Cr)", callback_data=f"dl_select:{j_id}:{f.format_id}")] for f in meta.available_formats[:6]]
        await msg.edit_text(f"📹 **Title:** *{meta.title}*\nSelect quality:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")

async def download_quality_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, j_id, fmt = q.data.split(":")
    cached = CACHE.get(j_id)
    if not cached:
        await q.edit_message_text("Expired session. Please resend the link.")
        return

    await q.edit_message_text("⏳ Generating direct download link...")
    try:
        direct = await download_service.process_and_deliver_download(j_id, q.from_user.id, fmt, cached["url"], cached["plat"], cached["meta"].title)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬇️ Download Video to Phone", url=direct)]])
        await q.edit_message_text("✅ Link Ready! Tap below to download:", reply_markup=kb)
    except Exception as e:
        await q.edit_message_text(f"❌ Error: {e}")