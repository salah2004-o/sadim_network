import glob
import os
from telebot import types
from yt_dlp import YoutubeDL
from ._paths import DOWNLOAD_DIR

FEATURES = [
    {"key": "download_instagram", "label": "تحميل إنستقرام", "description": "تحميل منشورات/ريلز/ستوريز إنستقرام العامة.", "help_line": None},
    {"key": "download_tiktok", "label": "تحميل تيك توك", "description": "تحميل فيديوهات تيك توك.", "help_line": None},
]

_INSTAGRAM_HOSTS = ["instagram.com", "/p/", "/reel/", "/reels/", "/stories/"]
_TIKTOK_HOSTS = ["tiktok.com"]


def _get_ydl_opts(chat_id, extra=None):
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


def _detect_content_type(url):
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


def _send_media_files(bot, chat_id, files, caption):
    images = [f for f in files if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
    videos = [f for f in files if not f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]

    if len(images) > 1:
        media_group = []
        opened = []
        for i, img_path in enumerate(images):
            fh = open(img_path, 'rb')
            opened.append(fh)
            media_group.append(types.InputMediaPhoto(
                fh,
                caption=caption if i == 0 else None,
                parse_mode="Markdown" if i == 0 else None
            ))
        bot.send_media_group(chat_id, media_group)
        for fh in opened:
            fh.close()
    elif len(images) == 1:
        with open(images[0], 'rb') as f:
            bot.send_photo(chat_id, f, caption=caption, parse_mode="Markdown")

    for vid_path in videos:
        with open(vid_path, 'rb') as f:
            bot.send_video(chat_id, f, caption=caption, parse_mode="Markdown", timeout=180)

    for file_path in files:
        try:
            os.remove(file_path)
        except Exception:
            pass


def register(bot, bot_id, enabled_features):
    ig_enabled = "download_instagram" in enabled_features
    tt_enabled = "download_tiktok" in enabled_features
    if not ig_enabled and not tt_enabled:
        return

    @bot.message_handler(func=lambda m: m.text and m.text.startswith("http"))
    def handle_download(message):
        url = message.text.strip()
        is_instagram = any(host in url for host in _INSTAGRAM_HOSTS)
        is_tiktok = any(host in url for host in _TIKTOK_HOSTS)

        if is_instagram and not ig_enabled:
            return
        if is_tiktok and not tt_enabled:
            return
        if not is_instagram and not is_tiktok:
            return

        content_type = _detect_content_type(url)
        type_labels = {
            'story': '📖 جاري تحميل الستوري...',
            'reel': '🎬 جاري تحميل الريل...',
            'post': '🖼 جاري تحميل البوست...',
            'tiktok': '🎵 جاري تحميل التيك توك...',
            'unknown': '⚙️ جاري سحب المحتوى...',
        }
        prog_msg = bot.reply_to(message, f"**{type_labels.get(content_type, '⚙️ جاري...')}**", parse_mode="Markdown")

        extra_opts = {'noplaylist': False} if content_type == 'story' else {}
        ydl_opts = _get_ydl_opts(message.chat.id, extra_opts)

        try:
            with YoutubeDL(ydl_opts) as ydl:
                ydl.extract_info(url, download=True)

            files = glob.glob(os.path.join(DOWNLOAD_DIR, f"*{message.chat.id}.*"))
            if not files:
                bot.edit_message_text(
                    "❌ المحتوى غير متاح أو محمي أو يتطلب تسجيل دخول (شائع مع الحسابات الخاصة بإنستقرام، أو حجب مؤقت من تيك توك).",
                    message.chat.id, prog_msg.message_id, parse_mode="Markdown")
                return

            count_label = f" ({len(files)} عناصر)" if len(files) > 1 else ""
            type_names = {'story': 'الستوري', 'reel': 'الريل', 'post': 'البوست', 'tiktok': 'التيك توك', 'unknown': 'المحتوى'}
            caption = (
                f"✅ **تم استخراج {type_names.get(content_type, 'المحتوى')}{count_label}**\n"
                f"🔗 **عبر سديم:** https://sadim.cloud/"
            )
            _send_media_files(bot, message.chat.id, files, caption)
            bot.delete_message(message.chat.id, prog_msg.message_id)
        except Exception as e:
            print(f"Download error: {e}")
            bot.edit_message_text("⚠️ حدث خطأ أثناء التحميل، حاول مرة أخرى لاحقاً.",
                                   message.chat.id, prog_msg.message_id, parse_mode="Markdown")
            for f in glob.glob(os.path.join(DOWNLOAD_DIR, f"*{message.chat.id}.*")):
                try:
                    os.remove(f)
                except Exception:
                    pass
