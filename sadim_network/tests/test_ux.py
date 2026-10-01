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


# ==================== عدم مضاعفة عدّ التحميل ====================

def test_repeat_download_same_session_counts_once_but_logs_both(client, temp_book):
    r1 = client.get(f"/library/{temp_book}/download", headers={"User-Agent": DESKTOP_UA})
    r2 = client.get(f"/library/{temp_book}/download", headers={"User-Agent": DESKTOP_UA})
    assert r1.status_code == 200 and r2.status_code == 200
    assert _download_count(temp_book) == 1

    rows = _events(event_type="download.success")
    assert len(rows) == 2                         # السجل الخام كامل
    assert sorted(r[5]["counted"] for r in rows) == [False, True]


def test_repeat_download_other_session_counts_again(client, temp_book):
    client.get(f"/library/{temp_book}/download", headers={"User-Agent": DESKTOP_UA})
    client.delete_cookie("sd_sid")                # زائر/جلسة أخرى
    client.get(f"/library/{temp_book}/download", headers={"User-Agent": DESKTOP_UA})
    assert _download_count(temp_book) == 2


def test_repeat_download_after_window_counts_again(client, temp_book):
    client.get(f"/library/{temp_book}/download", headers={"User-Agent": DESKTOP_UA})
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE analytics_events SET occurred_at = NOW() - INTERVAL '31 minutes' WHERE event_type = 'download.success'")
    conn.commit()
    cur.close()
    conn.close()
    client.get(f"/library/{temp_book}/download", headers={"User-Agent": DESKTOP_UA})
    assert _download_count(temp_book) == 2


# ==================== المهمة 1: الصفحة الوسيطة للتحميل ====================

EXTERNAL_NAV = {**BROWSER_HEADERS, "Sec-Fetch-Dest": "document", "Sec-Fetch-Site": "none", "Sec-Fetch-Mode": "navigate"}
INTERNAL_NAV = {**BROWSER_HEADERS, "Sec-Fetch-Dest": "document", "Sec-Fetch-Site": "same-origin", "Sec-Fetch-Mode": "navigate"}


def test_external_download_link_shows_page_without_counting(client, temp_book):
    r = client.get(f"/library/{temp_book}/download", headers=EXTERNAL_NAV)
    assert r.status_code == 200
    assert "attachment" not in r.headers.get("Content-Disposition", "")
    html = r.get_data(as_text=True)
    assert f"/library/{temp_book}/download?direct=1" in html
    assert "PYTEST_TEST_BOOK" in html
    assert _download_count(temp_book) == 0
    assert _events(event_type="download.success") == []


def test_internal_download_click_still_sends_file(client, temp_book):
    r = client.get(f"/library/{temp_book}/download", headers=INTERNAL_NAV)
    assert "attachment" in r.headers.get("Content-Disposition", "")
    assert _download_count(temp_book) == 1


def test_link_preview_bot_gets_page_not_file(client, temp_book):
    r = client.get(f"/library/{temp_book}/download", headers={"User-Agent": "TelegramBot (like TwitterBot)"})
    assert r.status_code == 200
    assert "attachment" not in r.headers.get("Content-Disposition", "")
    assert _download_count(temp_book) == 0


def test_direct_param_sends_file_and_marks_via(client, temp_book):
    r = client.get(f"/library/{temp_book}/download?direct=1", headers=EXTERNAL_NAV)
    assert "attachment" in r.headers.get("Content-Disposition", "")
    rows = _events(event_type="download.success")
    assert len(rows) == 1 and rows[0][5]["via"] == "download_page"


def test_download_page_views_do_not_consume_download_limit(client, temp_book):
    for _ in range(12):
        assert client.get(f"/library/{temp_book}/download", headers=EXTERNAL_NAV).status_code == 200
    r = client.get(f"/library/{temp_book}/download?direct=1", headers=EXTERNAL_NAV)
    assert r.status_code == 200
    assert "attachment" in r.headers.get("Content-Disposition", "")


def test_similar_books_prefers_co_downloads(client, temp_book):
    from app.models.library_mdl import Library
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO books (title, desc_text, pdf_path, cover_path, download_count) VALUES ('PYTEST_CO', 'و', 'x.pdf', 'x.jpg', 0) RETURNING id")
    co_id = cur.fetchone()[0]
    cur.execute("INSERT INTO books (title, desc_text, pdf_path, cover_path, download_count) VALUES ('PYTEST_POPULAR', 'و', 'y.pdf', 'y.jpg', 1000000) RETURNING id")
    popular_id = cur.fetchone()[0]
    for book in (temp_book, co_id):
        cur.execute(
            "INSERT INTO analytics_events (event_type, session_id, visitor_type, metadata) VALUES ('download.success', 'pytest-sess', 'human', %s)",
            (json.dumps({"book_id": book}),),
        )
    conn.commit()
    try:
        similar = Library.get_similar_books(temp_book, limit=2)
        # الأكثر تحميلاً مع هذا الكتاب أولاً، ثم يكمل بالأكثر تحميلاً عموماً
        assert [b["id"] for b in similar] == [co_id, popular_id]
    finally:
        cur.execute("DELETE FROM books WHERE id IN (%s, %s)", (co_id, popular_id))
        conn.commit()
        cur.close()
        conn.close()


# ==================== المهمة 1: التلخيص من صفحة الرواية ====================

def test_book_summary_is_cached_and_logs_both_events(client, temp_book, monkeypatch):
    calls = []

    def fake_summarize(title, content, content_type, preferred, user_id=None):
        calls.append(title)
        return {"content": "- نقطة أولى\n- نقطة ثانية", "provider": "gemini", "tools": []}

    monkeypatch.setattr("app.routes.ai.summarize_content", fake_summarize)
    payload = json.dumps({"type": "book", "id": temp_book, "source": "book_page"})

    r1 = client.post("/ai/summarize", data=payload, content_type="application/json", headers=BROWSER_HEADERS)
    r2 = client.post("/ai/summarize", data=payload, content_type="application/json", headers=BROWSER_HEADERS)
    assert r1.get_json()["provider"] == "gemini"
    assert r2.get_json()["provider"] == "cache"
    assert len(calls) == 1                         # النموذج استُدعي مرة واحدة فقط

    used = _events(event_type="ai_summarize_used")
    assert len(used) == 2 and all(r[5]["source"] == "book_page" for r in used)
    assert len(_events(event_type="ai_summarize.from_book_page")) == 2


def test_summary_without_source_keeps_old_event_shape(client, temp_book, monkeypatch):
    monkeypatch.setattr("app.routes.ai.summarize_content",
                        lambda *a, **k: {"content": "ملخص", "provider": "local", "tools": []})
    client.post("/ai/summarize", data=json.dumps({"type": "book", "id": temp_book}),
                content_type="application/json", headers=BROWSER_HEADERS)
    rows = _events(event_type="ai_summarize_used")
    assert set(rows[0][5].keys()) == {"context_type", "context_id", "provider"}
    assert _events(event_type="ai_summarize.from_book_page") == []
    from app.models.library_mdl import Library
    assert Library.get_ai_summary(temp_book) is None   # البديل المحلي لا يُخزَّن


def test_editing_book_clears_cached_summary(temp_book):
    from app.models.library_mdl import Library
    Library.set_ai_summary(temp_book, "قديم")
    book = Library.get_book_id(temp_book)
    Library.edit_book("PYTEST_TEST_BOOK", "وصف جديد", book["cover_path"], book["pdf_path"], temp_book)
    assert Library.get_ai_summary(temp_book) is None


def test_book_page_shows_summary_button_to_guests(client, temp_book):
    html = client.get(f"/library/{temp_book}", headers=BROWSER_HEADERS).get_data(as_text=True)
    assert 'id="summarize-btn"' in html
    assert "source: 'book_page'" in html
