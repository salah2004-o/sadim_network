# -*- coding: utf-8 -*-
"""
اختبارات تطوير البوتات (أكتوبر 2026): مشرف بوتات المستخدمين، الجدولة، رسائل الكتب، ومسارات لوحة التحكم.
لا اتصال بتيليجرام إطلاقاً: التشغيل/الإيقاف والتحقق من التوكن وRedis كلها بدائل وهمية.

التشغيل: من مجلد sadim_network/  →  REDIS_URL= RATELIMIT_STORAGE_URI=memory:// pytest tests/test_bots.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("BOT_WORKER", "false")

import json

import pytest

from app.db.sadim_db import get_db_connection
from app.config import settings
from app.bot import supervisor, bot_runner
from test_analytics import client, clean_analytics, temp_user, temp_book  # noqa: F401

BROWSER_HEADERS = {"User-Agent": "Mozilla/5.0 (Linux; Android 13) Chrome/129 Mobile", "Accept": "text/html", "Accept-Language": "ar"}


class FakeRedis:
    """يكفي ما يستخدمه المشرف: set/get/expire/delete، مجموعة، وhash."""

    def __init__(self):
        self.kv, self.sets, self.hashes = {}, {}, {}

    @staticmethod
    def _b(v):
        return v if isinstance(v, bytes) else str(v).encode()

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.kv:
            return None
        self.kv[key] = self._b(value)
        return True

    def get(self, key):
        return self.kv.get(key)

    def expire(self, key, ttl):
        return key in self.kv

    def delete(self, *keys):
        return sum(self.kv.pop(k, None) is not None for k in keys)

    def sadd(self, key, value):
        self.sets.setdefault(key, set()).add(self._b(value))

    def spop(self, key):
        members = self.sets.get(key)
        return members.pop() if members else None

    def hset(self, key, field, value):
        self.hashes.setdefault(key, {})[self._b(field)] = self._b(value)

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def hdel(self, key, field):
        self.hashes.get(key, {}).pop(self._b(field), None)


class FakeRunner:
    """بديل start_bot/stop_bot/running_snapshot — يسجّل ما طلبه المشرف."""

    def __init__(self):
        self.running = {}   # bot_id -> {"token", "fingerprint", "alive"}
        self.started, self.stopped = [], []

    def start_bot(self, bot_id, token, channel, fingerprint=None):
        self.running[bot_id] = {"token": token, "fingerprint": fingerprint, "alive": True}
        self.started.append(bot_id)

    def stop_bot(self, token):
        for bot_id, info in list(self.running.items()):
            if info["token"] == token:
                del self.running[bot_id]
                self.stopped.append(bot_id)

    def running_snapshot(self):
        return {k: dict(v) for k, v in self.running.items()}


@pytest.fixture
def fake_env(monkeypatch):
    redis = FakeRedis()
    runner = FakeRunner()
    monkeypatch.setattr(settings, "SESSION_REDIS", redis)
    monkeypatch.setattr(bot_runner, "start_bot", runner.start_bot)
    monkeypatch.setattr(bot_runner, "stop_bot", runner.stop_bot)
    monkeypatch.setattr(bot_runner, "running_snapshot", runner.running_snapshot)
    monkeypatch.setattr(supervisor, "_token_is_valid", lambda bot_id, token: not token.startswith("BAD"))
    return redis, runner


@pytest.fixture
def temp_bots(temp_user):
    conn = get_db_connection()
    cur = conn.cursor()
    ids = {}
    for name, token, active in (("good", "111:GOOD-pytest", True), ("bad", "BAD:pytest", True), ("off", "222:OFF-pytest", False)):
        cur.execute("INSERT INTO bots (user_id, bot_token, channel, is_active) VALUES (%s, %s, '@pytest_channel', %s) RETURNING id",
                    (temp_user, token, active))
        ids[name] = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    yield ids
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM bots WHERE id = ANY(%s)", (list(ids.values()),))
    conn.commit()
    cur.close()
    conn.close()


def _set_active(bot_id, active):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE bots SET is_active = %s WHERE id = %s", (active, bot_id))
    conn.commit()
    cur.close()
    conn.close()


# ==================== المشرف ====================

def test_reconcile_starts_only_active_bots_with_valid_tokens(fake_env, temp_bots):
    redis, runner = fake_env
    supervisor.reconcile()
    assert temp_bots["good"] in runner.running
    assert temp_bots["bad"] not in runner.running and temp_bots["off"] not in runner.running
    statuses = supervisor.get_statuses()
    assert statuses[temp_bots["good"]]["state"] == "running"


def test_reconcile_stops_deactivated_bot_and_clears_status(fake_env, temp_bots):
    redis, runner = fake_env
    supervisor.reconcile()
    _set_active(temp_bots["good"], False)
    supervisor.reconcile()
    assert temp_bots["good"] not in runner.running
    assert temp_bots["good"] in runner.stopped
    assert temp_bots["good"] not in supervisor.get_statuses()


def test_feature_change_restarts_bot(fake_env, temp_bots):
    from app.models.bot_feature_model import BotFeature
    redis, runner = fake_env
    supervisor.reconcile()
    BotFeature.set_enabled(temp_bots["good"], "quotes", False)
    supervisor.reconcile()
    assert runner.stopped.count(temp_bots["good"]) == 1
    assert runner.started.count(temp_bots["good"]) == 2


def test_restart_request_and_dead_thread_restart_bot(fake_env, temp_bots):
    redis, runner = fake_env
    supervisor.reconcile()
    supervisor.request_restart(temp_bots["good"])
    supervisor.reconcile()
    assert runner.started.count(temp_bots["good"]) == 2
    runner.running[temp_bots["good"]]["alive"] = False      # خيط البوت مات لأي سبب
    supervisor.reconcile()
    assert runner.started.count(temp_bots["good"]) == 3


def test_only_one_instance_holds_the_lock(fake_env, monkeypatch):
    redis, _ = fake_env
    assert supervisor._acquire_or_renew_lock() is True
    assert supervisor._acquire_or_renew_lock() is True              # نفس النسخة تجدّد
    monkeypatch.setattr(supervisor, "_instance_id", "other-host:999")
    assert supervisor._acquire_or_renew_lock() is False             # نسخة ثانية تنتظر


def test_record_error_maps_telegram_errors(fake_env):
    supervisor.record_error(7, Exception("Error code: 409. Conflict: terminated by other getUpdates request"))
    assert supervisor.get_statuses()[7]["state"] == "error"
    supervisor.record_error(7, Exception("Error code: 401. Unauthorized"))
    assert supervisor.get_statuses()[7]["state"] == "token_invalid"


def test_importing_app_does_not_start_bots():
    import app  # noqa: F401
    assert supervisor._thread is None
    assert bot_runner._running_bots == {}


# ==================== الجدولة ====================

def test_scheduler_uses_utc_and_stops():
    from app.bot import scheduler
    scheduler.start_scheduler(interval_hours=24)
    try:
        # APScheduler 3.11 (محلياً) يحوّلها لـ zoneinfo؛ 3.6 على السيرفر يشترط pytz — يُفحص هناك قبل النشر
        assert str(scheduler._scheduler.timezone) == "UTC"
        assert {job.id for job in scheduler._scheduler.get_jobs()} == {"book_announce", "bot_limit_reminders"}
    finally:
        scheduler.stop_scheduler()
    assert scheduler._scheduler is None


# ==================== رسائل الكتب ====================

def test_telegram_safety_escaping_links_and_late_callbacks():
    from telebot.apihelper import ApiTelegramException
    from app.bot.telegram_safety import h, site_link, harden

    assert h("<b>*بعد الجنازة*</b>") == "&lt;b&gt;*بعد الجنازة*&lt;/b&gt;"
    link = site_link("/library/5/read", "daily_novel", "bot_3")
    assert link.endswith("/library/5/read?utm_source=telegram&utm_medium=bot&utm_campaign=daily_novel&utm_content=bot_3")

    class FakeBot:
        def answer_callback_query(self, *a, **k):
            raise ApiTelegramException("answerCallbackQuery", None, {"error_code": 400, "description": "Bad Request: query is too old and response timeout expired or query ID is invalid"})
    bot = harden(FakeBot())
    assert bot.answer_callback_query("id") is False                # لا يقطع المعالج


def test_announcement_message_is_escaped_html_with_utm_buttons():
    from app.bot.scheduler import announcement_message
    caption, markup = announcement_message({"id": 11, "title": "رواية «بعد الجنازة» *After the Funeral*", "desc_text": "<script>"}, bot_id=3)
    assert "<b>رواية «بعد الجنازة» *After the Funeral*</b>" in caption
    assert "&lt;script&gt;" in caption
    urls = [btn.url for row in markup.keyboard for btn in row]
    assert any("/library/11/read?" in u and "utm_campaign=channel_announce" in u and "utm_content=bot_3" in u for u in urls)


def test_daily_novel_message_is_html():
    from app.bot.services import daily_novel
    text, markup, _ = daily_novel._prepare_message({"id": 2, "title": "a_b*c", "desc_text": "x & y", "cover_path": ""})
    assert "<b>a_b*c</b>" in text and "x &amp; y" in text and "**" not in text
    assert any("utm_campaign=daily_novel" in btn.url for row in markup.keyboard for btn in row)


# ==================== لوحة التحكم ====================

def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["role"] = "user"


def test_dashboard_toggle_requests_reconcile_instead_of_running_bot(client, temp_user, temp_bots, monkeypatch):
    calls = []
    monkeypatch.setattr("app.routes.bots.bot.request_reconcile", lambda: calls.append("reconcile"))
    monkeypatch.setattr(bot_runner, "start_bot", lambda *a, **k: pytest.fail("لا تشغيل للبوت داخل عامل الموقع"))
    _login(client, temp_user)
    r = client.post(f"/bots/toggle/{temp_bots['good']}", headers=BROWSER_HEADERS)
    assert r.status_code == 302 and calls == ["reconcile"]


def test_dashboard_restart_requests_restart(client, temp_user, temp_bots, monkeypatch):
    calls = []
    monkeypatch.setattr("app.routes.bots.bot.request_restart", lambda bot_id: calls.append(bot_id))
    _login(client, temp_user)
    client.post(f"/bots/restart/{temp_bots['good']}", headers=BROWSER_HEADERS)
    assert calls == [temp_bots["good"]]


def test_bot_list_shows_runtime_status(client, temp_user, temp_bots, monkeypatch):
    monkeypatch.setattr("app.routes.bots.bot.get_statuses",
                        lambda: {temp_bots["good"]: {"state": "running"}, temp_bots["bad"]: {"state": "token_invalid", "detail": "x"}})
    _login(client, temp_user)
    html = client.get("/bots/", headers=BROWSER_HEADERS).get_data(as_text=True)
    assert "يعمل الآن" in html and "التوكن غير صالح" in html


# ==================== إصلاحات قديمة ====================

def test_ai_delete_works_via_post_because_nginx_blocks_delete(client, temp_user):
    _login(client, temp_user)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO ai_conversations (user_id, title) VALUES (%s, 'pytest') RETURNING id", (temp_user,))
    conv_id = cur.fetchone()[0]
    conn.commit()
    r = client.post(f"/ai/conversations/{conv_id}/delete", headers=BROWSER_HEADERS)
    assert r.status_code == 204
    cur.execute("SELECT COUNT(*) FROM ai_conversations WHERE id = %s", (conv_id,))
    assert cur.fetchone()[0] == 0
    cur.close()
    conn.close()
    assert client.post("/ai/guest/messages/clear", headers=BROWSER_HEADERS).status_code == 204


def test_article_views_are_counted_once_per_session(client, temp_user):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO posts (user_id, title, content) VALUES (%s, 'PYTEST_VIEWS', 'محتوى') RETURNING id", (temp_user,))
    post_id = cur.fetchone()[0]
    conn.commit()
    try:
        client.get(f"/articles/{post_id}", headers=BROWSER_HEADERS)
        client.get(f"/articles/{post_id}", headers=BROWSER_HEADERS)
        cur.execute("SELECT views FROM posts WHERE id = %s", (post_id,))
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT COUNT(*) FROM post_views WHERE post_id = %s", (post_id,))
        assert cur.fetchone()[0] == 1
    finally:
        cur.execute("DELETE FROM posts WHERE id = %s", (post_id,))
        conn.commit()
        cur.close()
        conn.close()


def test_library_allows_more_than_five_requests_per_minute(client, temp_book):
    from app.limiter import limiter
    limiter.reset()
    codes = [client.get(f"/library/{temp_book}", headers=BROWSER_HEADERS).status_code for _ in range(8)]
    assert codes == [200] * 8
