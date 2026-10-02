# مشرف بوتات المستخدمين — يعمل في عملية واحدة فقط: خدمة sadim_bot (python -m app.bot.bot_library).
#
# لماذا: كانت البوتات تُشغَّل عند استيراد التطبيق في كل عامل gunicorn، فتتكرر (تعارض 409 مع تيليجرام)،
# وتتوقف مع كل إعادة تحميل للموقع، وأوامر لوحة التحكم تصل لعامل عشوائي. والجدولة كانت تُسقط العامل كاملاً
# (APScheduler 3.6 + tzlocal 5) فلم تعمل البوتات ولا النشر التلقائي منذ آخر إعادة تشغيل.
#
# كيف:
# - كل RECONCILE_SECONDS (أو فوراً عند طلب من لوحة التحكم عبر Redis) يقرأ البوتات المفعّلة من القاعدة
#   ويطابق المشغَّل معها: يشغّل الجديد، يوقف المحذوف/الموقوف، ويعيد تشغيل ما تغيّر توكنه أو قناته أو ميزاته.
# - قفل Redis بنبض: نسخة واحدة فقط تشغّل البوتات والجدولة؛ لو توقفت يتسلّمها غيرها خلال دقيقة.
# - حالة كل بوت تُكتب في Redis لتعرضها لوحة "أدواتي".
import json
import os
import signal
import socket
import threading
import time

from app.config import settings
from app.bot import bot_runner

LOCK_KEY = "sadim:bots:supervisor_lock"
LOCK_TTL = 60
DIRTY_KEY = "sadim:bots:dirty"
RESTART_KEY = "sadim:bots:restart"
STATUS_KEY = "sadim:bots:status"
RECONCILE_SECONDS = 30
TICK_SECONDS = 3
TOKEN_RECHECK_SECONDS = 600

_instance_id = f"{socket.gethostname()}:{os.getpid()}"
_thread = None
_stop = threading.Event()
_holding_lock = False
_invalid_tokens = {}   # bot_id -> (token, checked_at)


def _redis():
    return settings.SESSION_REDIS


# ==================== واجهة لوحة التحكم (تُستدعى من عمّال الموقع) ====================

def request_reconcile():
    """لوحة التحكم تكتب في القاعدة ثم تطلب مطابقة فورية (بدل تشغيل البوت داخل عامل الموقع)."""
    r = _redis()
    if r:
        try:
            r.set(DIRTY_KEY, "1", ex=300)
        except Exception as e:
            print("⚠️ request_reconcile:", e)


def request_restart(bot_id):
    r = _redis()
    if r:
        try:
            r.sadd(RESTART_KEY, int(bot_id))
            r.set(DIRTY_KEY, "1", ex=300)
        except Exception as e:
            print("⚠️ request_restart:", e)


def get_statuses():
    """{bot_id: {"state", "detail", "at"}} — state: running | stopped | token_invalid | error | starting."""
    r = _redis()
    if not r:
        return {}
    try:
        raw = r.hgetall(STATUS_KEY)
    except Exception:
        return {}
    statuses = {}
    for key, value in raw.items():
        try:
            statuses[int(key)] = json.loads(value)
        except (ValueError, TypeError):
            continue
    return statuses


# ==================== الحالة ====================

def _set_status(bot_id, state, detail=None):
    r = _redis()
    if not r:
        return
    try:
        r.hset(STATUS_KEY, int(bot_id), json.dumps({"state": state, "detail": (detail or "")[:200], "at": int(time.time())}, ensure_ascii=False))
    except Exception:
        pass


def _clear_status(bot_id):
    r = _redis()
    if r:
        try:
            r.hdel(STATUS_KEY, int(bot_id))
        except Exception:
            pass


def record_error(bot_id, exception):
    """من ExceptionHandler البوت: 409 = نسخة أخرى تستخدم نفس التوكن، 401 = توكن ملغى."""
    text = str(exception)
    if "409" in text or "Conflict" in text:
        _set_status(bot_id, "error", "التوكن مستخدم في مكان آخر (409)")
    elif "401" in text or "Unauthorized" in text:
        _set_status(bot_id, "token_invalid", "التوكن ملغى أو غير صالح")
    else:
        _set_status(bot_id, "error", text)


# ==================== القفل ====================

def _acquire_or_renew_lock():
    """True لو هذه النسخة هي المسؤولة. بلا Redis (تطوير محلي) أو عند تعطّله: نعمل (عملية واحدة فعلياً)."""
    r = _redis()
    if not r:
        return True
    try:
        if r.set(LOCK_KEY, _instance_id, nx=True, ex=LOCK_TTL):
            return True
        holder = r.get(LOCK_KEY)
        if holder is not None and holder.decode() == _instance_id:
            r.expire(LOCK_KEY, LOCK_TTL)
            return True
        return False
    except Exception as e:
        print("⚠️ قفل مشرف البوتات (Redis):", e)
        return _holding_lock


def _release_lock():
    r = _redis()
    if not r:
        return
    try:
        holder = r.get(LOCK_KEY)
        if holder is not None and holder.decode() == _instance_id:
            r.delete(LOCK_KEY)
    except Exception:
        pass


# ==================== المطابقة ====================

def _desired_bots():
    """{bot_id: (token, channel, fingerprint)} للبوتات المفعّلة. البصمة تتغير مع التوكن/القناة/الميزات."""
    from app.models.bot_model import Bot
    desired = {}
    for b in Bot.get_active_bots():
        features = tuple(sorted(bot_runner.get_enabled_features(b.id)))
        desired[b.id] = (b.bot_token, b.channel, (b.bot_token, b.channel, features))
    return desired


def _token_is_valid(bot_id, token):
    """يتحقق من التوكن قبل التشغيل حتى لا يملأ توكن ملغى السجل بأخطاء 401 كل ثانية."""
    cached = _invalid_tokens.get(bot_id)
    if cached and cached[0] == token and time.time() - cached[1] < TOKEN_RECHECK_SECONDS:
        return False
    import telebot
    from telebot.apihelper import ApiTelegramException
    try:
        telebot.TeleBot(token, threaded=False).get_me()
        _invalid_tokens.pop(bot_id, None)
        return True
    except ApiTelegramException as e:
        if e.error_code == 401:
            _invalid_tokens[bot_id] = (token, time.time())
            _set_status(bot_id, "token_invalid", "التوكن ملغى أو غير صالح")
            return False
        return True   # خطأ مؤقت من تيليجرام: نحاول التشغيل، وinfinity_polling يعيد المحاولة
    except Exception:
        return True


def _pop_restart_requests():
    r = _redis()
    if not r:
        return set()
    try:
        ids = set()
        while True:
            item = r.spop(RESTART_KEY)
            if item is None:
                break
            ids.add(int(item))
        return ids
    except Exception:
        return set()


def _refresh_running_statuses(running):
    """خطأ مؤقت (شبكة، 502 من تيليجرام) لا يبقى ظاهراً للأبد: بعد 5 دقائق بلا أخطاء جديدة يرجع "يعمل"."""
    statuses = get_statuses()
    now = time.time()
    for bot_id, info in running.items():
        if not info["alive"]:
            continue
        current = statuses.get(bot_id)
        if current is None or (current.get("state") == "error" and now - current.get("at", 0) > 300):
            _set_status(bot_id, "running")


def reconcile():
    desired = _desired_bots()
    running = bot_runner.running_snapshot()
    restarts = _pop_restart_requests()
    _refresh_running_statuses(running)

    for bot_id, info in running.items():
        want = desired.get(bot_id)
        if want is None or want[2] != info["fingerprint"] or not info["alive"] or bot_id in restarts:
            bot_runner.stop_bot(info["token"])
            if want is None:
                _clear_status(bot_id)

    running = bot_runner.running_snapshot()
    for bot_id, (token, channel, fingerprint) in desired.items():
        if bot_id in running:
            continue
        if not _token_is_valid(bot_id, token):
            continue
        try:
            bot_runner.start_bot(bot_id, token, channel, fingerprint=fingerprint)
            _set_status(bot_id, "running")
        except Exception as e:
            _set_status(bot_id, "error", str(e))
            print(f"⚠️ فشل تشغيل البوت #{bot_id}: {e}")


def _stop_all():
    for info in bot_runner.running_snapshot().values():
        bot_runner.stop_bot(info["token"])


# ==================== الحلقة ====================

def _loop():
    global _holding_lock
    last_reconcile = 0.0
    while not _stop.is_set():
        try:
            holding = _acquire_or_renew_lock()
            if holding and not _holding_lock:
                print(f"🤖 مشرف البوتات: تسلّمت التشغيل ({_instance_id})")
                from app.bot.scheduler import start_scheduler
                start_scheduler(interval_hours=settings.BOOK_ANNOUNCE_INTERVAL_HOURS)
                last_reconcile = 0.0
            elif not holding and _holding_lock:
                print("🤖 مشرف البوتات: نسخة أخرى تسلّمت التشغيل — أوقف بوتاتي")
                _stop_all()
                from app.bot.scheduler import stop_scheduler
                stop_scheduler()
            _holding_lock = holding

            if holding:
                dirty = False
                r = _redis()
                if r:
                    try:
                        dirty = bool(r.delete(DIRTY_KEY))
                    except Exception:
                        pass
                if dirty or time.time() - last_reconcile >= RECONCILE_SECONDS:
                    reconcile()
                    last_reconcile = time.time()
        except Exception as e:
            print("⚠️ مشرف البوتات:", e)
        _stop.wait(TICK_SECONDS)


def _shutdown(*_args):
    _stop.set()
    _stop_all()
    _release_lock()
    os._exit(0)


def start():
    """يُستدعى مرة واحدة من خدمة sadim_bot قبل تشغيل البوت الرئيسي."""
    global _thread
    if _thread is not None or not settings.BOT_WORKER:
        return
    if threading.current_thread() is threading.main_thread():
        # systemd يرسل SIGTERM عند الإيقاف/إعادة التشغيل: نحرّر القفل فوراً فتتسلّم النسخة الجديدة بلا انتظار
        signal.signal(signal.SIGTERM, _shutdown)
    _thread = threading.Thread(target=_loop, name="bot-supervisor", daemon=True)
    _thread.start()
