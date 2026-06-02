import telebot
import os
import threading
import glob
import time
from flask import Blueprint, request, jsonify
from yt_dlp import YoutubeDL

bot_bp = Blueprint('bot_api', __name__)

DOWNLOAD_DIR = "downloads"
SADIM_URL = "https://sadim.cloud/"

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)



def text_to_binary(text):
    return ' '.join(format(byte, '08b') for byte in text.encode('utf-8'))



def sdm_header(title):
    return f"✨ **شبكة سديم | {title}**\n" + "—" * 22



def get_ydl_opts(chat_id, extra=None):
    """خيارات yt-dlp الموحدة مع دعم الكوكيز"""
    opts = {
        'format': 'best',
        'outtmpl': os.path.join(DOWNLOAD_DIR, f'%(id)s_{chat_id}.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'user_agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36'
        ),
    }
    if os.path.exists('cookies.txt'):
        opts['cookiefile'] = 'cookies.txt'
    if extra:
        opts.update(extra)
    return opts


def send_media_files(bot, chat_id, files, caption):
    """إرسال الملفات — صور أو فيديوهات، مع دعم الألبوم"""
    images = [f for f in files if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
    videos = [f for f in files if not f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]

    # إرسال الألبوم إذا صور متعددة
    if len(images) > 1:
        media_group = []
        opened = []
        for i, img_path in enumerate(images):
            fh = open(img_path, 'rb')
            opened.append(fh)
            media = telebot.types.InputMediaPhoto(
                fh,
                caption=caption if i == 0 else None,
                parse_mode="Markdown" if i == 0 else None
            )
            media_group.append(media)
        bot.send_media_group(chat_id, media_group)
        for fh in opened:
            fh.close()
    elif len(images) == 1:
        with open(images[0], 'rb') as f:
            bot.send_photo(chat_id, f, caption=caption, parse_mode="Markdown")

    for vid_path in videos:
        with open(vid_path, 'rb') as f:
            bot.send_video(chat_id, f, caption=caption, parse_mode="Markdown", timeout=180)

    # حذف الملفات بعد الإرسال
    for file_path in files:
        try:
            os.remove(file_path)
        except Exception:
            pass


def detect_content_type(url):
    """تحديد نوع المحتوى من الرابط"""
    url = url.lower()
    if '/stories/' in url:
        return 'story'
    elif '/reel/' in url or '/reels/' in url:
        return 'reel'
    elif '/p/' in url:
        return 'post'
    elif 'tiktok.com' in url:
        return 'tiktok'
    return 'unknown'


def start_bot_worker(bot_token, user_id):
    try:
        bot = telebot.TeleBot(bot_token, threaded=True)

        # ترحيب
        @bot.message_handler(commands=['start'])
        def start(message):
            welcome = (
                f"{sdm_header('المنصة الذكية')}\n\n"
                "🚀 **أهلاً بك في نظام سديم المتكامل**\n\n"
                "📌 **الخدمات المتاحة:**\n"
                "• 📥 **بوست إنستا:** أرسل رابط `/p/`\n"
                "• 🎬 **ريل:** أرسل رابط `/reel/`\n"
                "• 📖 **ستوري:** أرسل رابط `/stories/`\n"
                "• 🎵 **تيك توك:** أرسل رابط tiktok.com\n"
                "• 👤 **معلومات:** `/info` + اليوزر\n"
                "• 🔢 **ثنائي:** `/binary` + النص\n\n"
                f"🌐 [زيارة موقعنا الرسمي]({SADIM_URL})\n"
                "🛡 _Powered by Sadim Cloud_"
            )
            bot.reply_to(message, welcome, parse_mode="Markdown", disable_web_page_preview=True)

        # معلومات الحساب
        @bot.message_handler(commands=['info'])
        def get_account_info(msg):
            username = msg.text.replace('/info', '').strip().replace('@', '')
            if not username:
                bot.reply_to(msg, "⚠️ مثال: `/info username`", parse_mode="Markdown")
                return

            status = bot.reply_to(msg, "🔍 **جاري فحص البيانات...**", parse_mode="Markdown")
            ydl_opts = {'quiet': True, 'no_warnings': True, 'extract_flat': True}
            if os.path.exists('cookies.txt'):
                ydl_opts['cookiefile'] = 'cookies.txt'

            try:
                with YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(f"https://instagram.com/{username}/", download=False)
                    res = (
                        f"{sdm_header('معلومات الحساب')}\n\n"
                        f"👤 **الاسم:** `{info.get('uploader', 'غير معروف')}`\n"
                        f"📊 **المتابعين:** `{info.get('follower_count', 'N/A')}`\n"
                        f"✅ **التوثيق:** `{'موثق ★' if info.get('is_verified') else 'حساب عادي'}`\n\n"
                        f"🌐 [مزيد من الأدوات]({SADIM_URL})"
                    )
                    bot.edit_message_text(res, msg.chat.id, status.message_id,
                                          parse_mode="Markdown", disable_web_page_preview=True)
            except Exception:
                bot.edit_message_text("❌ تعذر الوصول للحساب أو أنه خاص.",
                                      msg.chat.id, status.message_id, parse_mode="Markdown")

        # تحويل ثنائي
        @bot.message_handler(commands=['binary'])
        def convert_to_binary(msg):
            text = msg.text.replace('/binary', '').strip()
            if text:
                res = (
                    f"{sdm_header('نتائج التحويل')}\n\n"
                    f"✅ **النص:** `{text}`\n"
                    f"🔢 **الثنائي:**\n`{text_to_binary(text)}`\n\n"
                    f"🔗 {SADIM_URL}"
                )
                bot.reply_to(msg, res, parse_mode="Markdown")

        # معالج التحميل الرئيسي
        @bot.message_handler(func=lambda m: m.text and m.text.startswith("http"))
        def handle_download(msg):
            url = msg.text.strip()

            supported = any(d in url for d in [
                "tiktok.com", "instagram.com", "/p/", "/reel/", "/reels/", "/stories/"
            ])
            if not supported:
                return

            content_type = detect_content_type(url)

            type_labels = {
                'story':   '📖 جاري تحميل الستوري...',
                'reel':    '🎬 جاري تحميل الريل...',
                'post':    '🖼 جاري تحميل البوست...',
                'tiktok':  '🎵 جاري تحميل التيك توك...',
                'unknown': '⚙️ جاري سحب المحتوى...',
            }
            prog_msg = bot.reply_to(msg, f"**{type_labels.get(content_type, '⚙️ جاري...')}**",
                                    parse_mode="Markdown")

            # خيارات خاصة بالستوري — تحميل كل الصور/الفيديوهات
            extra_opts = {}
            if content_type == 'story':
                extra_opts = {'noplaylist': False}

            ydl_opts = get_ydl_opts(msg.chat.id, extra_opts)

            try:
                with YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)

                files = glob.glob(os.path.join(DOWNLOAD_DIR, f"*{msg.chat.id}.*"))

                if not files:
                    bot.edit_message_text("❌ المحتوى غير متاح أو محمي أو تطلب تسجيل دخول.",
                                          msg.chat.id, prog_msg.message_id, parse_mode="Markdown")
                    return

                # عدد العناصر للتوضيح في الكابشن
                count_label = f" ({len(files)} عناصر)" if len(files) > 1 else ""

                type_names = {
                    'story':   'الستوري',
                    'reel':    'الريل',
                    'post':    'البوست',
                    'tiktok':  'التيك توك',
                    'unknown': 'المحتوى',
                }

                caption = (
                    f"✅ **تم استخراج {type_names.get(content_type, 'المحتوى')}{count_label}**\n"
                    f"👤 **الناشر:** {info.get('uploader', 'N/A') if isinstance(info, dict) else 'N/A'}\n\n"
                    f"🔗 **عبر سديم:** {SADIM_URL}"
                )

                send_media_files(bot, msg.chat.id, files, caption)
                bot.delete_message(msg.chat.id, prog_msg.message_id)

            except Exception as e:
                print(f"Download error: {e}")
                bot.edit_message_text("⚠️ حدث خطأ أثناء التحميل، حاول مرة أخرى لاحقاً.",
                                      msg.chat.id, prog_msg.message_id, parse_mode="Markdown")
                # تنظيف أي ملفات ناقصة
                for f in glob.glob(os.path.join(DOWNLOAD_DIR, f"*{msg.chat.id}.*")):
                    try:
                        os.remove(f)
                    except Exception:
                        pass

        bot.send_message(user_id,
                         f"✅ **نظام سديم:** تم تفعيل البوت وربطه بـ {SADIM_URL}",
                         parse_mode="Markdown")
        bot.infinity_polling(timeout=60, long_polling_timeout=30)

    except Exception as e:
        print(f"Sadim System Error: {e}")


@bot_bp.route('/api/add_bots', methods=['POST'])
def add_bots():
    data = request.get_json()
    bot_token = data.get('bot_token')
    user_id = data.get('user_id')
    admin_token = data.get('admin_token')

    if admin_token != "123456":
        return jsonify({"error": "Unauthorized"}), 401

    threading.Thread(target=start_bot_worker, args=(bot_token, user_id), daemon=True).start()
    return jsonify({"message": "Sadim Bot Activated", "status": "success", "site": SADIM_URL}), 200