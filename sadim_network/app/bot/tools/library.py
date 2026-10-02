import os
from telebot import types
from models.library_mdl import Library
from app.bot.telegram_safety import book_buttons, h
from ._paths import UPLOAD_FOLDER

FEATURES = [
    {"key": "library", "label": "مكتبة أجاثا كريستي", "description": "تصفح وتحميل روايات أجاثا كريستي.",
     "help_line": "/library — مكتبة أجاثا كريستي"},
]


def send_library_list(bot, chat_id):
    """مستقلة عن أمر /library حتى يقدر زر قائمة /start يستدعيها مباشرة بنفس السلوك."""
    books = Library.get_all_books()
    if not books:
        bot.send_message(chat_id, "⚠️ لا توجد كتب بالمكتبة حالياً، جرّب لاحقاً.")
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for b in books:
        markup.add(types.InlineKeyboardButton(
            text=f"📖 {b.get('title', 'بدون عنوان')}",
            callback_data=f"book_{b.get('id')}"
        ))
    bot.send_message(
        chat_id,
        f"📚 لدينا {len(books)} رواية. اختر ما تريد تحميله:",
        reply_markup=markup
    )


def register(bot, bot_id, enabled_features):
    if "library" in enabled_features:
        @bot.message_handler(commands=['library'])
        def show_library(message):
            send_library_list(bot, message.chat.id)

    # زر تحميل الكتاب مشترك بين /library و/search — لازم يشتغل لو أي وحدة منهم مفعّلة
    if "library" in enabled_features or "search" in enabled_features:
        @bot.callback_query_handler(func=lambda c: c.data.startswith("book_"))
        def send_book(call):
            book_id = call.data.replace("book_", "")
            book = Library.get_book_id(book_id)
            if not book:
                bot.answer_callback_query(call.id, "❌ الكتاب غير موجود.")
                return

            bot.answer_callback_query(call.id, "⏳ جاري التجهيز...")
            title = book.get('title', 'بدون عنوان')
            pdf_path = os.path.join(UPLOAD_FOLDER, book.get('pdf_path', ''))
            cover_path = os.path.join(UPLOAD_FOLDER, book.get('cover_path', ''))
            user_id = call.from_user.id

            # زرّا القراءة على الموقع وصفحة الرواية (utm_content يميّز كل بوت مستخدم)
            markup = book_buttons(book['id'], "user_bot_library", f"bot_{bot_id}")
            if os.path.exists(cover_path):
                with open(cover_path, 'rb') as f:
                    bot.send_photo(user_id, f, caption=f"📖 <b>{h(title)}</b>", parse_mode="HTML", reply_markup=markup)
            else:
                bot.send_message(user_id, f"📖 <b>{h(title)}</b>", parse_mode="HTML", reply_markup=markup)

            if os.path.exists(pdf_path):
                with open(pdf_path, 'rb') as f:
                    bot.send_document(user_id, f)
            else:
                bot.send_message(user_id, "❌ الملف غير متوفر حالياً.")
