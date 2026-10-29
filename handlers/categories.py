from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from database.category_repo import category_repo

def build_kb(page=0):
    cats = category_repo.get_active_categories()
    items = cats[page*6 : (page+1)*6]
    kb, row = [], []
    for c in items:
        row.append(InlineKeyboardButton(f"{c.get('icon','📁')} {c['name']}", callback_data=f"cat_select:{c['slug']}"))
        if len(row) == 2: kb.append(row); row = []
    if row: kb.append(row)
    nav = []
    if page > 0: nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"cat_page:{page-1}"))
    if (page+1)*6 < len(cats): nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"cat_page:{page+1}"))
    if nav: kb.append(nav)
    return InlineKeyboardMarkup(kb)

async def show_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📁 **Select a Platform Category:**", parse_mode="Markdown", reply_markup=build_kb(0))

async def category_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data.startswith("cat_page:"):
        await q.edit_message_reply_markup(reply_markup=build_kb(int(q.data.split(":")[1])))
    elif q.data.startswith("cat_select:"):
        await q.message.reply_text(f"🔗 **{q.data.split(':')[1].title()} Selected!** Send public video URL:")