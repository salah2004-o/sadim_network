import io
import qrcode

FEATURES = [
    {"key": "qr", "label": "إنشاء رمز QR", "description": "تحويل أي نص أو رابط إلى صورة QR.",
     "help_line": "/qr <نص> — إنشاء رمز QR"},
]


def run_qr(bot, chat_id, content, bot_id=None):
    content = (content or "").strip()
    if not content:
        bot.send_message(chat_id, "⚠️ ما وصل أي نص، جرّب مرة ثانية.")
        return
    img = qrcode.make(content)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    bot.send_photo(chat_id, buf, caption="✅ رمز QR جاهز.")


def register(bot, bot_id, enabled_features):
    if "qr" not in enabled_features:
        return

    @bot.message_handler(commands=['qr'])
    def make_qr(message):
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            bot.reply_to(message, "⚠️ استخدم: /qr <نص أو رابط>\nمثال: /qr https://sadim.cloud")
            return
        run_qr(bot, message.chat.id, parts[1], bot_id)
