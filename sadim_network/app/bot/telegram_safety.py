# أدوات مشتركة لبوت سديم الرئيسي وبوتات المستخدمين: تحمي من أخطاء تيليجرام المتكررة في السجل،
# وتبني روابط الموقع بقياس (utm) حتى تظهر زيارات البوتات في لوحة التحليلات.
import html
from urllib.parse import urlencode

from telebot.apihelper import ApiTelegramException

# أنواع الرسائل التي تصل البوت — للمعالج الحارس الذي يبتلع ما لا يأتي من محادثة خاصة
ALL_CONTENT_TYPES = [
    "text", "photo", "voice", "document", "video", "audio", "sticker", "animation",
    "video_note", "location", "contact", "poll", "dice",
]


def harden(bot):
    """answer_callback_query يتجاهل "query is too old": الزر نفسه نجح، فقط تأكيد الضغط وصل متأخراً
    (كان يرمي استثناءً يقطع بقية المعالج — 13 مرة في أسبوع بسجل البوت الرئيسي)."""
    original = bot.answer_callback_query

    def safe_answer(*args, **kwargs):
        try:
            return original(*args, **kwargs)
        except ApiTelegramException as e:
            if "query is too old" in str(e) or "query ID is invalid" in str(e):
                return False
            raise

    bot.answer_callback_query = safe_answer
    return bot


def is_private(message):
    return getattr(message.chat, "type", None) == "private"


def h(text):
    """تهريب نص لـ parse_mode=HTML — عناوين الكتب فيها * و_ تكسر Markdown."""
    return html.escape(str(text or ""), quote=False)


def site_link(path, campaign, content=None):
    """رابط للموقع مع utm_source=telegram حتى تُنسب الزيارة للبوت في analytics_sessions."""
    from app.config import settings
    base = (settings.APP_URL or "https://sadim.cloud").rstrip("/")
    params = {"utm_source": "telegram", "utm_medium": "bot", "utm_campaign": campaign}
    if content:
        params["utm_content"] = content
    return f"{base}{path}?{urlencode(params)}"


def book_buttons(book_id, campaign, content=None):
    """زرّا "اقرأها على الموقع" (القارئ مباشرة) و"صفحة الرواية" (الملخص والآراء والتحميل)."""
    from telebot import types
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📖 اقرأها على الموقع", url=site_link(f"/library/{book_id}/read", campaign, content)),
        types.InlineKeyboardButton("📄 صفحة الرواية", url=site_link(f"/library/{book_id}", campaign, content)),
    )
    return markup
