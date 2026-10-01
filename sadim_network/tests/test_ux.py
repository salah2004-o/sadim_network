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


# ==================== المهمة 5: المشاركة و Open Graph ====================

def _with_real_cover(book_id):
    from PIL import Image
    from app.routes.shared import UPLOAD_FOLDER
    Image.new("RGB", (400, 600), (40, 70, 110)).save(os.path.join(UPLOAD_FOLDER, "pytest_cover.jpg"))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE books SET cover_path = 'pytest_cover.jpg' WHERE id = %s", (book_id,))
    conn.commit()
    cur.close()
    conn.close()


def test_book_page_has_full_open_graph_with_clean_url(client, temp_book):
    _with_real_cover(temp_book)
    html = client.get(f"/library/{temp_book}?ref=share", headers=BROWSER_HEADERS).get_data(as_text=True)
    assert f'<meta property="og:url" content="http://localhost/library/{temp_book}">' in html
    assert '<meta property="og:image" content="http://localhost/static/uploads/pytest_cover.jpg">' in html
    assert '<meta property="og:image:width" content="400">' in html
    assert '<meta property="og:image:height" content="600">' in html
    assert '<meta property="og:locale" content="ar_AR">' in html
    assert f'data-share-url="http://localhost/library/{temp_book}?ref=share"' in html


def test_download_page_has_open_graph_for_link_previews(client, temp_book):
    _with_real_cover(temp_book)
    html = client.get(f"/library/{temp_book}/download", headers={"User-Agent": "WhatsApp/2.23"}).get_data(as_text=True)
    assert 'property="og:image"' in html and "PYTEST_TEST_BOOK" in html
    assert 'data-placement="download_page"' in html


def test_ref_share_landing_sets_session_source(client, temp_book):
    client.get(f"/library/{temp_book}?ref=share", headers=BROWSER_HEADERS)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT utm_source, utm_medium FROM analytics_sessions")
    assert cur.fetchone() == ("share", "share_link")
    cur.close()
    conn.close()
    from app.models.analytics_dashboard import get_dashboard_stats
    assert get_dashboard_stats("today")["sources"]["share"] == 1


def test_explicit_utm_wins_over_ref_share(client, temp_book):
    client.get(f"/library/{temp_book}?ref=share&utm_source=telegram_channel", headers=BROWSER_HEADERS)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT utm_source FROM analytics_sessions")
    assert cur.fetchone()[0] == "telegram_channel"
    cur.close()
    conn.close()


def test_article_share_links_carry_ref_share(client, temp_user):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO posts (user_id, title, content) VALUES (%s, 'PYTEST_POST', 'محتوى تجريبي') RETURNING id", (temp_user,))
    post_id = cur.fetchone()[0]
    conn.commit()
    try:
        html = client.get(f"/articles/{post_id}", headers=BROWSER_HEADERS).get_data(as_text=True)
        assert f'<meta property="og:url" content="http://localhost/articles/{post_id}">' in html
        assert f"ref%3Dshare" in html                      # روابط واتساب/تيليجرام مُرمَّزة
        assert 'data-share-link="whatsapp"' in html
    finally:
        cur.execute("DELETE FROM posts WHERE id = %s", (post_id,))
        conn.commit()
        cur.close()
        conn.close()


# ==================== المهمة 6: SEO ====================

import re
import xml.etree.ElementTree as ET


def _json_ld(html):
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    return [json.loads(b) for b in blocks]


def test_robots_txt_allows_search_engines_and_lists_sitemap(client):
    r = client.get("/robots.txt")
    assert r.status_code == 200 and r.mimetype == "text/plain"
    body = r.get_data(as_text=True)
    assert "User-agent: *\nAllow: /" in body
    assert "Sitemap: http://localhost/sitemap.xml" in body
    assert "Disallow: /dashboard" in body
    assert "Disallow: /library\n" not in body          # المكتبة وصفحات الكتب مسموحة
    assert _sessions() == []                           # لا جلسة تحليلية لطلبات الزواحف لهذا الملف


def test_sitemap_lists_books_and_articles(client, temp_book, temp_user):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO posts (user_id, title, content) VALUES (%s, 'PYTEST_POST', 'محتوى') RETURNING id", (temp_user,))
    post_id = cur.fetchone()[0]
    conn.commit()
    try:
        r = client.get("/sitemap.xml")
        assert r.status_code == 200 and r.mimetype == "application/xml"
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        locs = [el.text for el in ET.fromstring(r.data).findall("s:url/s:loc", ns)]
        assert f"http://localhost/library/{temp_book}" in locs
        assert f"http://localhost/articles/{post_id}" in locs
        assert "http://localhost/library" in locs
        assert _sessions() == []
    finally:
        cur.execute("DELETE FROM posts WHERE id = %s", (post_id,))
        conn.commit()
        cur.close()
        conn.close()


def test_book_page_has_clean_canonical_hreflang_and_book_schema(client, temp_book):
    html = client.get(f"/library/{temp_book}?ref=share&utm_source=x", headers=BROWSER_HEADERS).get_data(as_text=True)
    assert f'<link rel="canonical" href="http://localhost/library/{temp_book}">' in html
    assert f'<link rel="alternate" hreflang="ar" href="http://localhost/library/{temp_book}">' in html
    graph = _json_ld(html)[0]["@graph"]
    book = next(node for node in graph if node["@type"] == "Book")
    assert book["name"] == "PYTEST_TEST_BOOK" and book["inLanguage"] == "ar"
    assert any(node["@type"] == "BreadcrumbList" for node in graph)


def test_article_page_has_article_schema(client, temp_user):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO posts (user_id, title, content) VALUES (%s, 'PYTEST_POST', 'محتوى') RETURNING id", (temp_user,))
    post_id = cur.fetchone()[0]
    conn.commit()
    try:
        html = client.get(f"/articles/{post_id}?ref=share", headers=BROWSER_HEADERS).get_data(as_text=True)
        article = _json_ld(html)[0]
        assert article["@type"] == "Article" and article["headline"] == "PYTEST_POST"
        assert article["datePublished"]
        assert f'<link rel="canonical" href="http://localhost/articles/{post_id}">' in html
    finally:
        cur.execute("DELETE FROM posts WHERE id = %s", (post_id,))
        conn.commit()
        cur.close()
        conn.close()


def test_public_layout_canonical_drops_tracking_keeps_page(client):
    html = client.get("/about?ref=share&utm_source=x", headers=BROWSER_HEADERS).get_data(as_text=True)
    assert '<link rel="canonical" href="http://localhost/about">' in html
    html = client.get("/articles/?page=2", headers=BROWSER_HEADERS).get_data(as_text=True)
    assert '<link rel="canonical" href="http://localhost/articles/?page=2">' in html


def test_download_page_canonical_points_to_book(client, temp_book):
    html = client.get(f"/library/{temp_book}/download", headers=EXTERNAL_NAV).get_data(as_text=True)
    assert f'<link rel="canonical" href="http://localhost/library/{temp_book}">' in html
    assert 'content="noindex, follow"' in html


# ==================== المهمة 2: سبب حقيقي للتسجيل ====================

def _post_json(client, url, payload, method="post"):
    return getattr(client, method)(url, data=json.dumps(payload), content_type="application/json", headers=BROWSER_HEADERS)


def test_reading_progress_is_saved_and_restored_in_reader(client, temp_user, temp_book):
    _login(client, temp_user)
    r = _post_json(client, "/api/personal/progress", {"book_id": temp_book, "page": 37, "total_pages": 120})
    assert r.status_code == 200 and r.get_json()["status"] == "reading"
    html = client.get(f"/library/{temp_book}/read", headers=BROWSER_HEADERS).get_data(as_text=True)
    assert 'data-saved-page="37"' in html
    assert 'data-logged-in="1"' in html
    assert 'id="sd-signup-sheet"' not in html            # لا دعوة تسجيل لعضو


def test_reaching_last_page_marks_book_finished(client, temp_user, temp_book):
    _login(client, temp_user)
    r = _post_json(client, "/api/personal/progress", {"book_id": temp_book, "page": 120, "total_pages": 120})
    assert r.get_json()["status"] == "finished"


def test_invalid_progress_is_rejected(client, temp_user, temp_book):
    _login(client, temp_user)
    r = _post_json(client, "/api/personal/progress", {"book_id": temp_book, "page": 200, "total_pages": 120})
    assert r.status_code == 400


def test_progress_api_does_not_count_pageviews(client, temp_user, temp_book):
    _login(client, temp_user)
    client.get("/", headers=BROWSER_HEADERS)
    before = _sessions()[0][4]
    _post_json(client, "/api/personal/progress", {"book_id": temp_book, "page": 2, "total_pages": 10})
    assert _sessions()[0][4] == before


def test_guest_reader_has_signup_sheet_and_no_saved_page(client, temp_book):
    html = client.get(f"/library/{temp_book}/read", headers=BROWSER_HEADERS).get_data(as_text=True)
    assert 'id="sd-signup-sheet"' in html
    assert 'data-saved-page=""' in html and 'data-logged-in="0"' in html


def test_guest_shelf_shows_this_browser_downloads(client, temp_book):
    client.get(f"/library/{temp_book}/download", headers={**BROWSER_HEADERS, "Sec-Fetch-Dest": "document", "Sec-Fetch-Site": "same-origin"})
    html = client.get("/shelf", headers=BROWSER_HEADERS).get_data(as_text=True)
    assert "PYTEST_TEST_BOOK" in html
    assert 'data-placement="shelf_page"' in html


def test_downloads_before_signup_appear_on_member_shelf(client, temp_user, temp_book):
    # زائر يحمّل، ثم يسجّل دخوله في نفس المتصفح: الجلسة التحليلية تُربط بحسابه
    client.get(f"/library/{temp_book}/download", headers={**BROWSER_HEADERS, "Sec-Fetch-Dest": "document", "Sec-Fetch-Site": "same-origin"})
    _login(client, temp_user)
    client.get("/", headers=BROWSER_HEADERS)
    html = client.get("/shelf", headers=BROWSER_HEADERS).get_data(as_text=True)
    assert "حمّلتها" in html and "PYTEST_TEST_BOOK" in html


def test_book_alerts_subscribe_and_unsubscribe_by_token(client, temp_user):
    from app.models import shelf_model
    _login(client, temp_user)
    assert client.post("/api/personal/book-alerts", headers=BROWSER_HEADERS).get_json() == {"subscribed": True}
    assert shelf_model.is_subscribed(temp_user)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT unsubscribe_token FROM book_alert_subscriptions WHERE user_id = %s", (temp_user,))
    token = cur.fetchone()[0]
    cur.close()
    conn.close()
    client.get(f"/alerts/unsubscribe/{token}", headers=BROWSER_HEADERS)
    assert not shelf_model.is_subscribed(temp_user)


def test_new_book_notification_reaches_subscribers(temp_user, monkeypatch):
    from app.models import shelf_model
    sent = []
    monkeypatch.setattr("app.utlis.email_utils.send_new_book_email",
                        lambda email, title, url, cover, unsub: sent.append((email, title, unsub)) or True)
    shelf_model.subscribe(temp_user)
    assert shelf_model.notify_new_book("رواية جديدة", "https://x/library/1", "https://x/c.jpg", "https://x") == 1
    assert sent[0][0] == "pytest_analytics_user@example.com"
    assert sent[0][2].startswith("https://x/alerts/unsubscribe/")


class _FakeRedirect:
    def __call__(self, redirect_uri):
        from flask import redirect
        return redirect("https://accounts.google.com/o/oauth2/auth")


def test_google_login_keeps_only_internal_next(client, monkeypatch):
    monkeypatch.setattr("app.routes.loding.google_oauth.authorize_redirect", _FakeRedirect())
    client.get("/auth/google?next=/library/5/read&src=reader_exit&intent=book_alerts", headers=BROWSER_HEADERS)
    with client.session_transaction() as sess:
        assert sess["login_next"] == "/library/5/read"
        assert sess["login_src"] == "reader_exit"
        assert sess["login_intent"] == "book_alerts"
    for evil in ("//evil.com", "https://evil.com", r"/\evil.com"):
        client.get(f"/auth/google?next={evil}", headers=BROWSER_HEADERS)
        with client.session_transaction() as sess:
            assert "login_next" not in sess


def test_google_signup_returns_to_next_with_source_and_alerts(client, monkeypatch):
    from app.models import shelf_model
    monkeypatch.setattr("app.routes.loding.google_oauth.authorize_redirect", _FakeRedirect())
    monkeypatch.setattr("app.routes.loding.google_oauth.authorize_access_token", lambda: {"userinfo": {
        "email": "pytest_google_signup@example.com", "sub": "pytest-google-sub", "name": "Google Tester", "picture": ""}})
    client.get("/auth/google?next=/shelf&src=download_page&intent=book_alerts", headers=BROWSER_HEADERS)
    try:
        r = client.get("/auth/google/callback", headers=BROWSER_HEADERS)
        assert r.status_code == 302 and r.headers["Location"].endswith("/shelf")
        rows = _events(event_type="auth.register")
        assert len(rows) == 1 and rows[0][5]["source"] == "download_page"
        assert shelf_model.is_subscribed(rows[0][1])
    finally:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE email = 'pytest_google_signup@example.com'")
        conn.commit()
        cur.close()
        conn.close()


def test_book_page_guest_like_goes_through_google_with_next(client, temp_book):
    html = client.get(f"/library/{temp_book}", headers=BROWSER_HEADERS).get_data(as_text=True)
    assert f"/auth/google?next=/library/{temp_book}&amp;src=book_like" in html
    assert 'id="sd-signup-sheet"' in html


def test_admin_adding_book_triggers_alert_thread(client, temp_user, monkeypatch):
    import io as _io
    import threading as _threading
    from app.routes.shared import UPLOAD_FOLDER
    calls = []
    monkeypatch.setattr("app.models.shelf_model.notify_new_book", lambda *args: calls.append(args))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET role = 'admin' WHERE id = %s", (temp_user,))
    conn.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = temp_user
        sess["role"] = "admin"
    r = client.post("/dashboard/library/add", data={
        "title": "PYTEST_ALERT_BOOK", "desc": "وصف",
        "pdf_file": (_io.BytesIO(b"%PDF-1.4 x"), "b.pdf"),
        "cover_file": (_io.BytesIO(b"\xff\xd8\xff"), "c.jpg"),
    }, content_type="multipart/form-data", headers=BROWSER_HEADERS)
    for t in _threading.enumerate():
        if t is not _threading.current_thread() and t.daemon:
            t.join(timeout=2)
    try:
        assert r.status_code == 302
        assert len(calls) == 1 and calls[0][0] == "PYTEST_ALERT_BOOK"
        assert "/library/" in calls[0][1] and "/static/uploads/cover_" in calls[0][2]
    finally:
        cur.execute("SELECT pdf_path, cover_path FROM books WHERE title = 'PYTEST_ALERT_BOOK'")
        for pdf, cover in cur.fetchall():
            for name in (pdf, cover):
                try:
                    os.remove(os.path.join(UPLOAD_FOLDER, name))
                except OSError:
                    pass
        cur.execute("DELETE FROM books WHERE title = 'PYTEST_ALERT_BOOK'")
        conn.commit()
        cur.close()
        conn.close()
