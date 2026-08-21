import io
from gtts import gTTS

FEATURES = [
    {"key": "tts", "label": "تحويل النص لصوت", "description": "تحويل أي نص مكتوب إلى رسالة صوتية.",
     "help_line": "/tts <نص> — تحويل نص لصوت"},
]

MAX_CHARS = 500


def _detect_lang(text):
    return "ar" if any("؀" <= ch <= "ۿ" for ch in text) else "en"


def run_tts(bot, chat_id, text, bot_id=None):
    text = (text or "").strip()
    if not text:
        bot.send_message(chat_id, "⚠️ ما وصل أي نص، جرّب مرة ثانية.")
        return
    if len(text) > MAX_CHARS:
        bot.send_message(chat_id, f"⚠️ النص طويل جداً، الحد الأقصى {MAX_CHARS} حرف.")
        return

    try:
        audio = io.BytesIO()
        gTTS(text=text, lang=_detect_lang(text)).write_to_fp(audio)
        audio.seek(0)
        bot.send_voice(chat_id, audio)
    except Exception as e:
        print(f"TTS error: {e}")
        bot.send_message(chat_id, "⚠️ تعذّر تحويل النص لصوت، حاول مرة أخرى لاحقاً.")


def register(bot, bot_id, enabled_features):
    if "tts" not in enabled_features:
        return

    @bot.message_handler(commands=['tts'])
    def text_to_speech(message):
        parts = message.text.split(maxsplit=1)
        text = parts[1].strip() if len(parts) > 1 else ""
        if not text:
            bot.reply_to(message, "⚠️ استخدم: /tts <نص>\nمثال: /tts مرحباً بك في شبكة سديم")
            return
        run_tts(bot, message.chat.id, text, bot_id)
