# رفّ القارئ: مكان القراءة المحفوظ، وما حمّله، وما أعجبه، وتنبيه الكتب الجديدة.
# يقرأ من جداول موجودة (reading_history, book_likes, user_favorites, analytics_events/sessions)
# ولا يضيف إلا جدول الاشتراك في التنبيه.

import secrets

import psycopg2.extras

from app.db.sadim_db import get_db_connection


def save_progress(user_id, book_id, page, total_pages):
    """يحفظ آخر صفحة. الوصول للصفحة الأخيرة = أنهى الكتاب."""
    status = 'finished' if total_pages and page >= total_pages else 'reading'
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """UPDATE reading_history SET last_page = %s, total_pages = %s, status = %s, last_updated = NOW()
               WHERE user_id = %s AND content_type = 'book' AND book_id = %s""",
            (page, total_pages, status, user_id, book_id),
        )
        if cur.rowcount == 0:
            cur.execute(
                """INSERT INTO reading_history (user_id, content_type, book_id, status, last_page, total_pages)
                   VALUES (%s, 'book', %s, %s, %s, %s)""",
                (user_id, book_id, status, page, total_pages),
            )
        conn.commit()
        return status
    finally:
        conn.close()


def get_saved_page(user_id, book_id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT last_page FROM reading_history WHERE user_id = %s AND content_type = 'book' AND book_id = %s",
            (user_id, book_id),
        )
        row = cur.fetchone()
        return row[0] if row and row[0] else None
    finally:
        conn.close()


_DOWNLOADS_SQL = """
    SELECT b.id, b.title, b.cover_path, MAX(e.occurred_at) AS downloaded_at
    FROM analytics_events e
    JOIN books b ON b.id::text = e.metadata->>'book_id'
    WHERE e.event_type = 'download.success' AND ({where})
    GROUP BY b.id, b.title, b.cover_path
    ORDER BY downloaded_at DESC
    LIMIT 30
"""


def get_downloads(user_id=None, session_id=None):
    """الكتب التي حمّلها: بحسابه، أو من أي جلسة رُبطت بحسابه لاحقاً (فما حمّله قبل التسجيل
    يظهر في رفّه بعده). للزائر: ما حمّله من هذا المتصفح فقط."""
    if user_id:
        where = "e.user_id = %s OR e.session_id IN (SELECT session_id FROM analytics_sessions WHERE user_id = %s)"
        params = (user_id, user_id)
    elif session_id:
        where, params = "e.session_id = %s", (session_id,)
    else:
        return []
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(_DOWNLOADS_SQL.format(where=where), params)
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_shelf(user_id):
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT b.id, b.title, b.cover_path, h.status, h.last_page, h.total_pages, h.last_updated
            FROM reading_history h JOIN books b ON b.id = h.book_id
            WHERE h.user_id = %s AND h.content_type = 'book'
            ORDER BY (h.status = 'reading') DESC, h.last_updated DESC
            LIMIT 30
        """, (user_id,))
        reading = [dict(row) for row in cur.fetchall()]
        cur.execute("""
            SELECT b.id, b.title, b.cover_path, MAX(t.added_at) AS added_at FROM (
                SELECT book_id, created_at AS added_at FROM book_likes WHERE user_id = %s
                UNION ALL
                SELECT book_id, added_at FROM user_favorites WHERE user_id = %s AND content_type = 'book'
            ) t JOIN books b ON b.id = t.book_id
            GROUP BY b.id, b.title, b.cover_path
            ORDER BY added_at DESC
            LIMIT 30
        """, (user_id, user_id))
        liked = [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()
    return {
        "reading": reading,
        "downloaded": get_downloads(user_id=user_id),
        "liked": liked,
        "alerts": is_subscribed(user_id),
    }


# ==================== تنبيه الكتب الجديدة ====================

def is_subscribed(user_id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM book_alert_subscriptions WHERE user_id = %s", (user_id,))
        return cur.fetchone() is not None
    finally:
        conn.close()


def subscribe(user_id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO book_alert_subscriptions (user_id, unsubscribe_token) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING",
            (user_id, secrets.token_urlsafe(32)),
        )
        conn.commit()
    finally:
        conn.close()


def unsubscribe(user_id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM book_alert_subscriptions WHERE user_id = %s", (user_id,))
        conn.commit()
    finally:
        conn.close()


def unsubscribe_by_token(token):
    """إلغاء بضغطة من رابط البريد (بدون تسجيل دخول)."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM book_alert_subscriptions WHERE unsubscribe_token = %s", (token,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_alert_recipients():
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT u.email, s.unsubscribe_token
            FROM book_alert_subscriptions s JOIN users u ON u.id = s.user_id
            WHERE u.status = 'active' AND u.email IS NOT NULL
        """)
        return cur.fetchall()
    finally:
        conn.close()


def notify_new_book(title, book_url, cover_url, app_url):
    """يُشغَّل في خيط خلفي بعد إضافة كتاب من لوحة الإدارة — فشل إرسال رسالة لا يوقف البقية."""
    from app.utlis.email_utils import send_new_book_email
    sent = 0
    for email, token in get_alert_recipients():
        try:
            if send_new_book_email(email, title, book_url, cover_url, f"{app_url}/alerts/unsubscribe/{token}"):
                sent += 1
        except Exception as e:
            print(f"Failed to send new-book alert to {email}:", e)
    print(f"📚 تنبيه رواية جديدة «{title}»: أُرسل إلى {sent} مشترك")
    return sent
