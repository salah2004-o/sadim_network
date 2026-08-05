# نشر تلقائي مجدوَل لروايات المكتبة الجديدة بقنوات البوتات المربوطة + تذكيرات حد البوتات
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from app.bot.bot_runner import _running_bots, _running_bots_lock

_scheduler = None


def announce_next_books():
    """يمر على كل بوت نشط، يشوف إذا فيه رواية أحدث من آخر رواية أعلنها، وينشرها بقناته."""
    from app.models.bot_model import Bot
    from app.models.library_mdl import Library

    for b in Bot.get_active_bots():
        if not b.channel:
            continue

        book = Library.get_next_for_bot(b.last_announced_book_id)
        if not book:
            continue

        with _running_bots_lock:
            entry = _running_bots.get(b.bot_token)

        if not entry or not entry.get("bot"):
            continue  # البوت مو شغال بالذاكرة حالياً (موقوف/لسا قيد التجهيز) — نتجاهله هالدورة

        telebot_instance = entry["bot"]
        title = book.get('title', 'بدون عنوان')
        desc = (book.get('desc_text') or '')[:250]
        caption = f"📖 **رواية جديدة بمكتبتنا:**\n\n*{title}*\n\n{desc}"

        try:
            import os
            from app.bot.tools._paths import UPLOAD_FOLDER
            cover_path = os.path.join(UPLOAD_FOLDER, book.get('cover_path') or '')
            if os.path.exists(cover_path):
                with open(cover_path, 'rb') as f:
                    telebot_instance.send_photo(b.channel, f, caption=caption, parse_mode="Markdown")
            else:
                telebot_instance.send_message(b.channel, caption, parse_mode="Markdown")

            Bot.update_last_announced(b.id, book['id'])
        except Exception as e:
            print(f"⚠️ فشل نشر الرواية بقناة البوت #{b.id}: {e}")


def check_bot_limit_reminders():
    """يمر يومياً على استثناءات حد البوتات: يرسل تذكير قبل 7 أيام من الانتهاء، وإيميل
    عند الانتهاء الفعلي — كل مرة مرة وحدة بس (أعلام reminder_*_sent تمنع التكرار)."""
    from app.models.bot_limit_model import BotLimitGrant
    from app.utlis.email_utils import send_bot_limit_reminder_email

    for grant in BotLimitGrant.get_expiring_within_days(7):
        days_left = (grant["expires_at"] - datetime.now()).days
        try:
            send_bot_limit_reminder_email(grant["email"], grant["username"], days_left, grant["expires_at"], is_final=False)
            BotLimitGrant.mark_reminder_sent(grant["user_id"], "7d")
        except Exception as e:
            print(f"⚠️ فشل إرسال تذكير حد البوتات (٧ أيام) للمستخدم #{grant['user_id']}: {e}")

    for grant in BotLimitGrant.get_freshly_expired():
        try:
            send_bot_limit_reminder_email(grant["email"], grant["username"], 0, grant["expires_at"], is_final=True)
            BotLimitGrant.mark_reminder_sent(grant["user_id"], "expiry")
        except Exception as e:
            print(f"⚠️ فشل إرسال إشعار انتهاء حد البوتات للمستخدم #{grant['user_id']}: {e}")


def start_scheduler(interval_hours=24):
    global _scheduler
    if _scheduler is not None:
        return  # مشغّل أصلاً بهالعملية
    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(announce_next_books, 'interval', hours=interval_hours, id='book_announce')
    _scheduler.add_job(check_bot_limit_reminders, 'interval', hours=24, id='bot_limit_reminders')
    _scheduler.start()
