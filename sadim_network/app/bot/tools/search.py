from telebot import types
from models.library_mdl import Library

FEATURES = [
    {"key": "search", "label": "البحث داخل المكتبة", "description": "بحث عن رواية بالاسم داخل المكتبة.",
     "help_line": "/search <كلمة> — بحث داخل المكتبة"},
]


def run_search(bot, chat_id, query, bot_id=None):
    query = (query or "").strip()
    if not query:
        bot.send_message(chat_id, "⚠️ ما وصل أي نص، جرّب مرة ثانية.")
        return

    results = Library.search_books(query)
    if not results:
        bot.send_message(chat_id, f"😕 ما لقيت أي رواية بعنوان يحتوي \"{query}\". جرّب /library لعرض كل الروايات.")
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    for b in results:
        markup.add(types.InlineKeyboardButton(
            text=f"📖 {b.get('title', 'بدون عنوان')}",
            callback_data=f"book_{b.get('id')}"
        ))
    bot.send_message(chat_id, f"🔍 لقيت {len(results)} نتيجة لـ \"{query}\":", reply_markup=markup)


def register(bot, bot_id, enabled_features):
    if "search" not in enabled_features:
        return

    @bot.message_handler(commands=['search'])
    def search_library(message):
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            bot.reply_to(message, "⚠️ استخدم: /search <كلمة من عنوان الرواية>\nمثال: /search جريمة")
            return
        run_search(bot, message.chat.id, parts[1], bot_id)
