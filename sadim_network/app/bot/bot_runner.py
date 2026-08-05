import threading
import redis
import telebot
from telebot import types
from app.bot.tools import library, quotes, downloader, shortener, qr, binary, search, contact_owner

_running_bots = {}
_running_bots_lock = threading.Lock()

# قائمة أدوات البوت — إضافة أداة جديدة = ملف جديد بـ app/bot/tools/ يصدّر:
#   FEATURES = [{"key": ..., "label": ..., "description": ..., "help_line": ... أو None}, ...]
#   def register(bot, bot_id, enabled_features): ...   (يتحقق داخلياً من مفاتيحه بـ enabled_features)
# ثم سطر واحد هنا بالقائمة. بدون أي تعديل على بقية الملف أو لوحة تحكم الأدمن — تُقرأ تلقائياً من FEATURES.
TOOLS = [library, search, quotes, downloader, shortener, qr, binary, contact_owner]

# أيقونة + سلوك كل ميزة بقائمة /start التفاعلية — "hint" يظهر كنافذة منبثقة صغيرة عند
# الضغط على زر ميزة تحتاج مدخل (أمر بمعطى)، و None يعني الزر يشغّل الميزة مباشرة بدون مدخل.
TOOL_MENU = {
    "library": {"emoji": "📚", "hint": None},
    "search": {"emoji": "🔍", "hint": "🔍 استخدم:\n/search <كلمة من عنوان الرواية>\n\nمثال:\n/search جريمة"},
    "quotes": {"emoji": "✨", "hint": None},
    "download_instagram": {"emoji": "📸", "hint": "📸 أرسل رابط منشور/ريل/ستوري إنستقرام مباشرة بالمحادثة، وبيتم تحميله تلقائياً."},
    "download_tiktok": {"emoji": "🎵", "hint": "🎵 أرسل رابط فيديو تيك توك مباشرة بالمحادثة، وبيتم تحميله تلقائياً."},
    "shorten": {"emoji": "🔗", "hint": "🔗 استخدم:\n/shorten <رابط>\n\nمثال:\n/shorten https://example.com"},
    "qr": {"emoji": "🔲", "hint": "🔲 استخدم:\n/qr <نص أو رابط>\n\nمثال:\n/qr https://sadim.cloud"},
    "binary": {"emoji": "🔢", "hint": "🔢 استخدم:\n/binary <نص>\n\nمثال:\n/binary سديم"},
    "contact_owner": {"emoji": "💬", "hint": "💬 أرسل أي رسالة عادية (مو أمر) بالمحادثة، وتوصل مباشرة لصاحب البوت — ويرد عليك من تيليجرامه."},
}


def get_all_features():
    """كتالوج كل ميزات البوتات الموجودة بالنظام — تُستخدم لبناء واجهة التفعيل/التعطيل بلوحة إدارة البوت."""
    features = []
    for tool in TOOLS:
        features.extend(getattr(tool, "FEATURES", []))
    return features


def get_enabled_features(bot_id):
    from app.models.bot_feature_model import BotFeature
    overrides = BotFeature.get_overrides(bot_id)
    return {f["key"] for f in get_all_features() if overrides.get(f["key"], True)}


def _register_handlers(bot: telebot.TeleBot, bot_id: int):
    enabled_features = get_enabled_features(bot_id)

    # تتبّع نشاط خفيف لإحصائيات لوحة الأدمن (مستخدمين/رسائل/أوامر) — يُسجَّل أولاً على كل رسالة
    # ثم يرجع ContinueHandling() حتى يكمل تيليجرام لبقية المعالجات المطابقة بشكل طبيعي (تيليجرام
    # يوقف عند أول معالج مطابق افتراضياً، وContinueHandling يلغي هذا التوقف لهذا المعالج فقط).
    @bot.message_handler(func=lambda m: True)
    def _track_activity(message):
        try:
            from app.models.bot_activity_model import BotActivity
            is_command = bool(message.text and message.text.startswith('/'))
            BotActivity.record(bot_id, message.chat.id, is_command)
        except Exception:
            pass
        return telebot.ContinueHandling()

    @bot.message_handler(commands=['start'])
    def start(message):
        buttons = []
        for tool in TOOLS:
            for feat in getattr(tool, "FEATURES", []):
                key = feat["key"]
                if key in enabled_features and key in TOOL_MENU:
                    emoji = TOOL_MENU[key]["emoji"]
                    buttons.append(types.InlineKeyboardButton(f"{emoji} {feat['label']}", callback_data=f"sadim_menu:{key}"))

        if buttons:
            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.add(*buttons)
            text = "🌌 <b>مرحباً بك في بوت شبكة سديم!</b>\n\nاختر أداة من الأزرار 👇 أو اكتب أمرها مباشرة."
        else:
            markup = None
            text = "🌌 <b>مرحباً بك في بوت شبكة سديم!</b>\n\nصاحب البوت ما فعّل أي ميزة بعد."

        bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=markup)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("sadim_menu:"))
    def handle_menu_button(call):
        key = call.data.split(":", 1)[1]
        meta = TOOL_MENU.get(key)
        if not meta:
            bot.answer_callback_query(call.id)
            return

        if key == "library":
            bot.answer_callback_query(call.id)
            library.send_library_list(bot, call.message.chat.id)
        elif key == "quotes":
            bot.answer_callback_query(call.id)
            quotes.send_next_quote(bot, bot_id, call.message.chat.id)
        else:
            bot.answer_callback_query(call.id, text=meta["hint"], show_alert=True)

    for tool in TOOLS:
        tool.register(bot, bot_id, enabled_features)


def start_bot(bot_id: int, bot_token: str, channel: str):
    with _running_bots_lock:
        if bot_token in _running_bots:
            return
        _running_bots[bot_token] = None  # حجز فوري يمنع أي نداء متزامن ثاني لنفس التوكن

    bot = telebot.TeleBot(bot_token, threaded=False)
    _register_handlers(bot, bot_id)
    t = threading.Thread(
        target=lambda: bot.infinity_polling(skip_pending=True),
        daemon=True
    )
    with _running_bots_lock:
        if bot_token not in _running_bots:
            return  # انحذف (stop_bot) وهو لسا قيد التجهيز — ما نشغّله
        _running_bots[bot_token] = {"bot": bot, "thread": t}
    t.start()


def stop_bot(bot_token: str):
    with _running_bots_lock:
        entry = _running_bots.pop(bot_token, None)
    if entry:
        entry["bot"].stop_polling()


def restore_all_bots():
    from app.models.bot_model import Bot
    from app.config import settings

    if not settings.BOT_WORKER:
        return

    if settings.SESSION_REDIS:
        try:
            acquired = settings.SESSION_REDIS.set("sadim:bots:worker_lock", "1", nx=True, ex=3600)
            if not acquired:
                return  # عملية/worker ثانية شغّلت البوتات بالفعل
        except redis.exceptions.RedisError as e:
            print(f"⚠️ تعذر الاتصال بـ Redis لأخذ قفل تشغيل البوتات، سيتم المتابعة بدونه: {e}")

    bots = Bot.get_all()
    for b in bots:
        if b.is_active:
            try:
                start_bot(b.id, b.bot_token, b.channel)
            except Exception as e:
                # بوت واحد معطوب (توكن فاسد، خطأ DB مؤقت...) ما يوقف بقية البوتات ولا يطيح التطبيق كامل
                print(f"⚠️ فشل تشغيل البوت #{b.id} عند الإقلاع، سيتم تجاهله والمتابعة: {e}")

    from app.bot.scheduler import start_scheduler
    start_scheduler(interval_hours=settings.BOOK_ANNOUNCE_INTERVAL_HOURS)
