import io
import qrcode

FEATURES = [
    {"key": "qr", "label": "إنشاء رمز QR", "description": "تحويل أي نص أو رابط إلى صورة QR.",
     "help_line": "/qr <نص> — إنشاء رمز QR"},
]


def register(bot, bot_id, enabled_features):
    if "qr" not in enabled_features:
        return

    @bot.message_handler(commands=['qr'])
    def make_qr(message):
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            bot.reply_to(message, "⚠️ استخدم: /qr <نص أو رابط>\nمثال: /qr https://sadim.cloud")
            return

        content = parts[1].strip()
        img = qrcode.make(content)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        bot.send_photo(message.chat.id, buf, caption="✅ رمز QR جاهز.")
