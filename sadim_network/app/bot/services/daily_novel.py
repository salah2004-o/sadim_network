import json
import os
import time
import threading
from datetime import datetime, timezone
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_HISTORY_PATH = _DATA_DIR / "daily_novels.json"
_LOCK = threading.Lock()

UPLOAD_FOLDER = os.path.join(
    Path(__file__).resolve().parent.parent.parent,
    "static", "uploads",
)

BOOKS_PER_SEND_BATCH = 30  # Telegram allows ~30 msg/s
_RATE_LIMIT_DELAY = 0.05  # seconds between sends to stay well under the limit


def _ensure_data_dir():
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_history():
    _ensure_data_dir()
    if not _HISTORY_PATH.exists():
        return {"history": []}
    try:
        with open(_HISTORY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict) or "history" not in data:
                return {"history": []}
            return data
    except (json.JSONDecodeError, IOError):
        return {"history": []}


def _save_history(data):
    _ensure_data_dir()
    tmp_path = str(_HISTORY_PATH) + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, _HISTORY_PATH)


def get_history():
    with _LOCK:
        return _load_history()["history"]


def _was_sent_today():
    """Check if a daily novel was already sent today (Asia/Riyadh timezone)."""
    import pytz
    riyadh = pytz.timezone("Asia/Riyadh")
    today_str = datetime.now(riyadh).strftime("%Y-%m-%d")
    with _LOCK:
        data = _load_history()
        for entry in reversed(data["history"]):
            sent_at = entry.get("sent_at", "")
            if sent_at and sent_at.startswith(today_str):
                return True
    return False


def _next_book():
    """Select the next book to send, avoiding ones already in history."""
    from app.models.library_mdl import Library
    all_books = Library.get_all_books()
    if not all_books:
        return None

    with _LOCK:
        data = _load_history()
        sent_ids = {e["book_id"] for e in data["history"]}

    candidates = [b for b in all_books if b["id"] not in sent_ids]
    if not candidates:
        candidates = all_books  # all have been sent — restart rotation
    candidates.sort(key=lambda b: b["id"], reverse=True)  # newest first
    return candidates[0]


def _build_book_url(book_id):
    from config.settings import APP_URL
    base = (APP_URL or "https://sadim.cloud").rstrip("/")
    return f"{base}/library/{book_id}"


def _prepare_message(book):
    from app.bot.tools._paths import UPLOAD_FOLDER as _upload_dir
    from app.bot.telegram_safety import h, book_buttons
    title = h(book.get("title", "بدون عنوان"))
    desc = h((book.get("desc_text") or "")[:250])
    cover_path = os.path.join(_upload_dir, book.get("cover_path") or "")

    # HTML مُهرَّب بدل Markdown (عناوين فيها * و_ كانت تُفشل الإرسال)، وزرّان بقياس utm
    markup = book_buttons(book["id"], "daily_novel")

    text = (
        f"📚 <b>رواية اليوم — شبكة سديم</b>\n\n"
        f"<b>{title}</b>\n\n"
        f"{desc}\n\n"
        f"<i>اقرأها على الموقع من الزر، أو تصفّح صفحتها.</i>"
    )
    return text, markup, cover_path


def _send_to_user(bot, user_id, text, markup, cover_path):
    """Send novel to a single user.  Raises on permanent failure (blocked)."""
    import telebot
    if os.path.exists(cover_path):
        with open(cover_path, "rb") as f:
            bot.send_photo(user_id, f, caption=text, reply_markup=markup, parse_mode="HTML")
    else:
        bot.send_message(user_id, text, reply_markup=markup, parse_mode="HTML")


def _send_daily_novel(bot, force=False):
    """Core send routine — returns a result dict or None if skipped."""
    from app.bot.services.users_db import get_active_users

    if not force and _was_sent_today():
        return {"skipped": True, "reason": "already_sent_today"}

    book = _next_book()
    if not book:
        return {"skipped": True, "reason": "no_books"}

    text, markup, cover_path = _prepare_message(book)
    active_users = get_active_users()

    success, failed = 0, 0

    for user in active_users:
        uid = user["id"]
        try:
            _send_to_user(bot, uid, text, markup, cover_path)
            # update last_seen
            from app.bot.services.users_db import touch_user
            touch_user(uid)
            success += 1
        except Exception as e:
            err = str(e).lower()
            if "blocked" in err or "privacy" in err or "not found" in err:
                from app.bot.services.users_db import deactivate_user
                deactivate_user(uid)
            failed += 1
        time.sleep(_RATE_LIMIT_DELAY)

    result = {
        "book_id": book["id"],
        "title": book.get("title", "بدون عنوان"),
        "sent_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "success": success,
        "failed": failed,
    }
    with _LOCK:
        data = _load_history()
        data["history"].append(result)
        _save_history(data)
    return result


def send_daily_novel(bot):
    """Scheduled entry-point — sends if not already sent today."""
    return _send_daily_novel(bot, force=False)


def send_daily_novel_now(bot):
    """Manual trigger from admin panel — always sends regardless."""
    return _send_daily_novel(bot, force=True)


def start_daily_scheduler(bot, hour, minute):
    """Start the APScheduler BackgroundScheduler for daily novel delivery.

    Returns the scheduler instance (or None if already running).
    """
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    import pytz

    scheduler = BackgroundScheduler(
        daemon=True,
        timezone=pytz.timezone("Asia/Riyadh"),
    )
    trigger = CronTrigger(
        hour=hour,
        minute=minute,
        timezone=pytz.timezone("Asia/Riyadh"),
    )
    scheduler.add_job(
        func=lambda: _run_scheduled(bot),
        trigger=trigger,
        id="daily_novel",
        replace_existing=True,
    )
    scheduler.start()
    return scheduler


_scheduler = None


def _run_scheduled(bot):
    """Wrapper called by APScheduler — logs errors so a crash doesn't kill the scheduler."""
    global _scheduler
    try:
        _send_daily_novel(bot, force=False)
    except Exception as e:
        print(f"⚠️ Daily novel send failed: {e}")


def ensure_scheduler_running(bot, hour, minute):
    """Call at startup — only creates one scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = start_daily_scheduler(bot, hour, minute)
    return _scheduler
