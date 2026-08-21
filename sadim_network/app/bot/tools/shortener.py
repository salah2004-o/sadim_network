FEATURES = [
    {"key": "shorten", "label": "اختصار الروابط", "description": "إنشاء رابط مختصر من أي رابط طويل.",
     "help_line": "/shorten <رابط> — اختصار رابط"},
]


def run_shorten(bot, chat_id, url, bot_id=None):
    url = (url or "").strip()
    if not url.startswith("http"):
        bot.send_message(chat_id, "⚠️ هذا مو رابط صحيح، لازم يبدأ بـ http. جرّب مرة ثانية.")
        return

    from app.models.short_link_model import ShortLink
    from app.config import settings

    code = ShortLink(original_url=url, bot_id=bot_id).add()
    short_url = f"{settings.APP_URL}/s/{code}"
    bot.send_message(chat_id, f"✅ رابطك المختصر:\n{short_url}")


def register(bot, bot_id, enabled_features):
    if "shorten" not in enabled_features:
        return

    @bot.message_handler(commands=['shorten'])
    def shorten(message):
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            bot.reply_to(message, "⚠️ استخدم: /shorten <رابط>\nمثال: /shorten https://example.com")
            return
        run_shorten(bot, message.chat.id, parts[1], bot_id)
