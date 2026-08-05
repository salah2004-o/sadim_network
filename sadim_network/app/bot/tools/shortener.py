FEATURES = [
    {"key": "shorten", "label": "اختصار الروابط", "description": "إنشاء رابط مختصر من أي رابط طويل.",
     "help_line": "/shorten <رابط> — اختصار رابط"},
]


def register(bot, bot_id, enabled_features):
    if "shorten" not in enabled_features:
        return

    @bot.message_handler(commands=['shorten'])
    def shorten(message):
        from app.models.short_link_model import ShortLink
        from app.config import settings

        parts = message.text.split(maxsplit=1)
        url = parts[1].strip() if len(parts) > 1 else ""
        if not url.startswith("http"):
            bot.reply_to(message, "⚠️ استخدم: /shorten <رابط>\nمثال: /shorten https://example.com")
            return

        code = ShortLink(original_url=url, bot_id=bot_id).add()
        short_url = f"{settings.APP_URL}/s/{code}"
        bot.send_message(message.chat.id, f"✅ رابطك المختصر:\n{short_url}")
