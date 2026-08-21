FEATURES = [
    {"key": "binary", "label": "تحويل النص إلى ثنائي", "description": "تحويل أي نص لتمثيله الثنائي (Binary).",
     "help_line": "/binary <نص> — تحويل نص إلى ثنائي"},
]


def run_binary(bot, chat_id, text, bot_id=None):
    text = (text or "").strip()
    if not text:
        bot.send_message(chat_id, "⚠️ ما وصل أي نص، جرّب مرة ثانية.")
        return
    binary = ' '.join(format(byte, '08b') for byte in text.encode('utf-8'))
    bot.send_message(chat_id, f"🔢 **النتيجة:**\n`{binary}`", parse_mode="Markdown")


def register(bot, bot_id, enabled_features):
    if "binary" not in enabled_features:
        return

    @bot.message_handler(commands=['binary'])
    def to_binary(message):
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            bot.reply_to(message, "⚠️ استخدم: /binary <نص>\nمثال: /binary سديم")
            return
        run_binary(bot, message.chat.id, parts[1], bot_id)
