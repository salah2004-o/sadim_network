FEATURES = [
    {"key": "binary", "label": "تحويل النص إلى ثنائي", "description": "تحويل أي نص لتمثيله الثنائي (Binary).",
     "help_line": "/binary <نص> — تحويل نص إلى ثنائي"},
]


def register(bot, bot_id, enabled_features):
    if "binary" not in enabled_features:
        return

    @bot.message_handler(commands=['binary'])
    def to_binary(message):
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            bot.reply_to(message, "⚠️ استخدم: /binary <نص>\nمثال: /binary سديم")
            return

        text = parts[1].strip()
        binary = ' '.join(format(byte, '08b') for byte in text.encode('utf-8'))
        bot.send_message(message.chat.id, f"🔢 **النتيجة:**\n`{binary}`", parse_mode="Markdown")
