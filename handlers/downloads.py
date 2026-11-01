import os, tempfile, httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from database.job_repo import job_repo
from database.user_repo import user_repo
from services.download_service import download_service, get_credit_price_for_quality
from logger import logger

def format_file_size(size_bytes: int) -> str:
    if not size_bytes or size_bytes <= 0: return ""
    mb = size_bytes / (1024 * 1024)
    if mb >= 1000: return f" (~{mb / 1024:.1f} GB)"
    return f" (~{mb:.1f} MB)"

async def handle_video_url_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text or not msg.text.strip().startswith("http"): return
    text = msg.text.strip()
    user = update.effective_user
    if user_repo.is_user_banned(user.id):
        await msg.reply_text("⛔ Your account has been suspended from downloading.")
        return

    status = await msg.reply_text("🔎 **Analyzing video link & checking qualities...**", parse_mode="Markdown")
    try:
        j_id, meta = await download_service.prepare_video_options(text, user.id)
    except Exception as e:
        await status.edit_text(f"❌ **Error:** {e}")
        return

    context.user_data[f"job_{j_id}"] = {"url": text, "platform": meta.platform, "title": meta.title}
    kb = []
    for f in meta.available_formats[:6]:
        cost = get_credit_price_for_quality(f.format_id)
        size_str = format_file_size(f.file_size_bytes)
        label = f"🎬 {f.label}{size_str} — 💰 {cost} Cr"
        kb.append([InlineKeyboardButton(label, callback_data=f"dl_select:{j_id}:{f.format_id}")])

    await status.delete()
    summary = f"📹 **Title:** *{meta.title}*\n🌐 **Platform:** `{meta.platform.title()}`\n\n👇 **Select download quality:**"
    if meta.thumbnail_url:
        try:
            await msg.reply_photo(photo=meta.thumbnail_url, caption=summary, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
            return
        except Exception: pass
    await msg.reply_text(summary, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def download_quality_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, j_id, fmt = q.data.split(":")
    cached = context.user_data.get(f"job_{j_id}")
    if not cached:
        persisted = job_repo.get_job(j_id)
        if persisted:
            cached = {"url": persisted.get("sanitized_url"), "platform": persisted.get("category_slug"), "title": persisted.get("original_url")}
    if not cached:
        await q.edit_message_text("⚠️ Download session expired. Please resend the video link.")
        return

    await q.edit_message_text(f"⏳ **Reserving credits & generating download for {fmt}...**", parse_mode="Markdown")
    try:
        direct = await download_service.process_and_deliver_download(
            j_id, q.from_user.id, fmt, cached["url"], cached["platform"], cached["title"]
        )
        delivered_in_chat = False
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                head_resp = await client.head(direct)
                content_len = int(head_resp.headers.get("content-length", 0))
                if 0 < content_len <= (20 * 1024 * 1024):
                    dl_resp = await client.get(direct)
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tf:
                        tf.write(dl_resp.content)
                        temp_p = tf.name
                    with open(temp_p, "rb") as vf:
                        await q.message.reply_video(video=vf, caption=f"🎬 {cached['title']}\nQuality: {fmt}")
                    os.remove(temp_p)
                    delivered_in_chat = True
        except Exception: pass

        markup = InlineKeyboardMarkup([[InlineKeyboardButton("⬇️ Download Video to Phone", url=direct)]])
        status_txt = "✅ **Video sent above!** You can also tap below to save directly:" if delivered_in_chat else "✅ **Download Link Ready!**\nTap below to download directly to your mobile device:"
        await q.edit_message_text(status_txt, parse_mode="Markdown", reply_markup=markup)
    except Exception as e:
        await q.edit_message_text(f"❌ {e}")