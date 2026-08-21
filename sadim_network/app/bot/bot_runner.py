import threading
import redis
import telebot
from telebot import types
from app.bot.tools import library, quotes, downloader, shortener, qr, binary, search, contact_owner, tts

_running_bots = {}
_running_bots_lock = threading.Lock()

# قائمة أدوات البوت — إضافة أداة جديدة = ملف جديد بـ app/bot/tools/ يصدّر:
#   FEATURES = [{"key": ..., "label": ..., "description": ..., "help_line": ... أو None}, ...]
#   def register(bot, bot_id, enabled_features): ...   (يتحقق داخلياً من مفاتيحه بـ enabled_features)
# ثم سطر واحد هنا بالقائمة. بدون أي تعديل على بقية الملف أو لوحة تحكم الأدمن — تُقرأ تلقائياً من FEATURES.
TOOLS = [library, search, quotes, downloader, shortener, qr, binary, tts, contact_owner]

# أيقونة كل ميزة بقائمة /start التفاعلية — سلوك الزر نفسه يتحدد بأي مجموعة تحته أدناه
# (تشغيل مباشر / طلب مدخل / رسالة توضيحية)، لا شيء هنا غير الأيقونة.
TOOL_MENU = {
    "library": {"emoji": "📚"},
    "search": {"emoji": "🔍"},
    "quotes": {"emoji": "✨"},
    "download_instagram": {"emoji": "📸"},
    "download_tiktok": {"emoji": "🎵"},
    "shorten": {"emoji": "🔗"},
    "qr": {"emoji": "🔲"},
    "binary": {"emoji": "🔢"},
    "tts": {"emoji": "🔊"},
    "contact_owner": {"emoji": "💬"},
}

# أدوات تحتاج مدخل نصي: بدل نافذة تلميح صغيرة تطلب من المستخدم يحفظ صيغة أمر ويكتبه يدوياً
# (مصدر إزعاج فعلي — "الأوامر غير واضحة")، الزر يسأل مباشرة وأي رد عادي بعده يُنفَّذ تلقائياً.
INPUT_TOOLS = {
    "search": (search.run_search, "🔍 اكتب كلمة من عنوان الرواية اللي تدور عليها:"),
    "shorten": (shortener.run_shorten, "🔗 أرسل الرابط اللي تبي تختصره:"),
    "qr": (qr.run_qr, "🔲 اكتب النص أو الرابط اللي تبي يتحول لرمز QR:"),
    "binary": (binary.run_binary, "🔢 اكتب النص اللي تبي تحوّله لثنائي:"),
    "tts": (tts.run_tts, "🔊 اكتب النص اللي تبي تحوّله لصوت:"),
}

# أدوات ما تحتاج أي أمر إطلاقاً — تعمل تلقائياً على أي رابط/رسالة، الزر فقط يوضّح كيف تُستخدم.
INFO_TOOLS = {
    "download_instagram": "📸 أرسل رابط منشور/ريل/ستوري إنستقرام هنا بالمحادثة، وبيتم تحميله تلقائياً.",
    "download_tiktok": "🎵 أرسل رابط فيديو تيك توك هنا بالمحادثة، وبيتم تحميله تلقائياً.",
    "contact_owner": "💬 أرسل أي رسالة عادية هنا بالمحادثة، وتوصل مباشرة لصاحب البوت — ويرد عليك من تيليجرامه.",
}

# تجميع الميزات بأقسام منطقية حتى تكون قائمة /start مريحة بدل شبكة أزرار مكدَّسة بلا تصنيف —
# كل ما تكبر TOOLS مستقبلاً، القسم يمتص الزيادة بدل ما الشاشة الأولى تطول.
CATEGORIES = [
    {"key": "content", "emoji": "📚", "label": "المكتبة والمحتوى", "tools": ["library", "search"]},
    {"key": "fun", "emoji": "✨", "label": "ترفيه", "tools": ["quotes"]},
    {"key": "tools", "emoji": "🛠", "label": "أدوات", "tools": ["qr", "binary", "shorten", "tts"]},
    {"key": "download", "emoji": "📥", "label": "تحميل من إنستقرام وتيك توك", "tools": ["download_instagram", "download_tiktok"]},
    {"key": "contact", "emoji": "💬", "label": "تواصل", "tools": ["contact_owner"]},
]


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

    def _active_categories():
        return [c for c in CATEGORIES if any(t in enabled_features for t in c["tools"])]

    def _category_buttons(cat, with_back):
        buttons = []
        for tool in TOOLS:
            for feat in getattr(tool, "FEATURES", []):
                key = feat["key"]
                if key in cat["tools"] and key in enabled_features and key in TOOL_MENU:
                    emoji = TOOL_MENU[key]["emoji"]
                    buttons.append(types.InlineKeyboardButton(f"{emoji} {feat['label']}", callback_data=f"sadim_menu:{key}"))
        if with_back:
            buttons.append(types.InlineKeyboardButton("🔙 رجوع", callback_data="sadim_root"))
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(*buttons)
        return markup

    def _root_markup(active_cats):
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(*[types.InlineKeyboardButton(f"{c['emoji']} {c['label']}", callback_data=f"sadim_cat:{c['key']}") for c in active_cats])
        return markup

    @bot.message_handler(commands=['start'])
    def start(message):
        active_cats = _active_categories()
        if not active_cats:
            bot.send_message(message.chat.id, "🌌 <b>مرحباً بك في بوت شبكة سديم!</b>\n\nصاحب البوت ما فعّل أي ميزة بعد.", parse_mode="HTML")
            return

        # قسم واحد فقط مفعّل: نعرض أدواته مباشرة بدون خطوة تصنيف زايدة تُتعِب المستخدم
        if len(active_cats) == 1:
            markup = _category_buttons(active_cats[0], with_back=False)
            text = "🌌 <b>مرحباً بك في بوت شبكة سديم!</b>\n\nاختر أداة من الأزرار 👇 أو اكتب أمرها مباشرة."
        else:
            markup = _root_markup(active_cats)
            text = "🌌 <b>مرحباً بك في بوت شبكة سديم!</b>\n\nاختر قسم من الأزرار 👇"

        bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=markup)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("sadim_cat:"))
    def handle_category(call):
        bot.answer_callback_query(call.id)
        cat = next((c for c in CATEGORIES if c["key"] == call.data.split(":", 1)[1]), None)
        if not cat:
            return
        bot.edit_message_text(
            f"{cat['emoji']} <b>{cat['label']}</b>\n\nاختر أداة 👇 أو اكتب أمرها مباشرة.",
            call.message.chat.id, call.message.message_id,
            parse_mode="HTML", reply_markup=_category_buttons(cat, with_back=True)
        )

    @bot.callback_query_handler(func=lambda c: c.data == "sadim_root")
    def handle_root(call):
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "🌌 <b>مرحباً بك في بوت شبكة سديم!</b>\n\nاختر قسم من الأزرار 👇",
            call.message.chat.id, call.message.message_id,
            parse_mode="HTML", reply_markup=_root_markup(_active_categories())
        )

    def _capture_reply(action):
        def handler(m):
            text = (m.text or "").strip()
            if text.startswith("/"):
                return  # المستخدم غيّر رأيه وكتب أمر ثاني بدل ما يرد — نتجاهل بصمت بدل معاملته كمدخل فعلي
            action(bot, m.chat.id, text, bot_id)
        return handler

    @bot.callback_query_handler(func=lambda c: c.data.startswith("sadim_menu:"))
    def handle_menu_button(call):
        key = call.data.split(":", 1)[1]
        if key not in TOOL_MENU:
            bot.answer_callback_query(call.id)
            return

        bot.answer_callback_query(call.id)
        if key == "library":
            library.send_library_list(bot, call.message.chat.id)
        elif key == "quotes":
            quotes.send_next_quote(bot, bot_id, call.message.chat.id)
        elif key in INPUT_TOOLS:
            action, prompt = INPUT_TOOLS[key]
            sent = bot.send_message(call.message.chat.id, prompt, reply_markup=types.ForceReply(selective=True))
            bot.register_next_step_handler(sent, _capture_reply(action))
        elif key in INFO_TOOLS:
            bot.send_message(call.message.chat.id, INFO_TOOLS[key])

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
