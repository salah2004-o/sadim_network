# -*- coding: utf-8 -*-
"""
اختبارات تطوير تجربة المستخدم (أكتوبر 2026) — نفس منهجية test_analytics.py:
قاعدة بيانات حقيقية + test_client، بيانات مؤقتة تُنشأ وتُحذف حول كل اختبار.

التشغيل: من مجلد sadim_network/  →  RATELIMIT_STORAGE_URI=memory:// pytest tests/test_ux.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("BOT_WORKER", "false")

import json

from app.db.sadim_db import get_db_connection
# fixtures مشتركة (clean_analytics تلقائية لكل اختبار هنا أيضاً)
from test_analytics import client, clean_analytics, temp_user, temp_book, _events, _sessions, DESKTOP_UA, MOBILE_UA  # noqa: F401

BROWSER_HEADERS = {"User-Agent": MOBILE_UA, "Accept": "text/html", "Accept-Language": "ar"}


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["role"] = "user"


def _download_count(book_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT download_count FROM books WHERE id = %s", (book_id,))
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return count


# ==================== الأساس: /api/events ====================

def test_client_event_whitelisted_is_logged_with_page_path(client):
    client.get("/", headers=BROWSER_HEADERS)  # ينشئ الجلسة التحليلية
    r = client.post("/api/events", data=json.dumps({
        "event": "share.clicked",
        "metadata": {"content_type": "book", "content_id": 7, "nested": {"x": 1}, "password": "x"},
        "path": "/library/7",
    }), content_type="application/json", headers=BROWSER_HEADERS)
    assert r.status_code == 204

    rows = _events(event_type="share.clicked")
    assert len(rows) == 1
    metadata = rows[0][5]
    assert metadata["content_id"] == 7
    assert "nested" not in metadata      # لا قيم متداخلة من الواجهة
    assert "password" not in metadata    # تنظيف المفاتيح الحساسة الموجود أصلاً

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT path FROM analytics_events WHERE event_type = 'share.clicked'")
    assert cur.fetchone()[0] == "/library/7"
    cur.close()
    conn.close()


def test_client_event_unknown_name_is_rejected(client):
    r = client.post("/api/events", data=json.dumps({"event": "download.success"}),
                    content_type="application/json", headers=BROWSER_HEADERS)
    assert r.status_code == 400
    assert _events(event_type="download.success") == []


def test_client_event_does_not_count_as_pageview(client):
    client.get("/", headers=BROWSER_HEADERS)
    before = _sessions()[0][4]
    client.post("/api/events", data=json.dumps({"event": "share.clicked"}),
                content_type="text/plain", headers=BROWSER_HEADERS)
    after = _sessions()[0][4]
    assert after == before
