FEATURES = [
    {"key": "quotes", "label": "الاقتباسات", "description": "إرسال اقتباس جديد من قائمة صاحب البوت عند الطلب.",
     "help_line": "/quote — اقتباس جديد"},
]


def send_next_quote(bot, bot_id, chat_id):
    """مستقلة عن أمر /quote حتى يقدر زر قائمة /start يستدعيها مباشرة بنفس السلوك."""
    from app.models.quote_model import Quote
    quote = Quote.get_next(bot_id)
    if not quote:
        bot.send_message(chat_id, "⚠️ لا توجد اقتباسات متاحة حالياً. صاحب البوت يقدر يضيف اقتباسات من صفحة إدارة البوت.")
        return
    text = f"✨ {quote.text}"
    if quote.author:
        text += f"\n\n— {quote.author}"
    bot.send_message(chat_id, text)
    Quote.mark_published(quote.id)


def register(bot, bot_id, enabled_features):
    if "quotes" not in enabled_features:
        return

    @bot.message_handler(commands=['quote'])
    def send_quote(message):
        send_next_quote(bot, bot_id, message.chat.id)
