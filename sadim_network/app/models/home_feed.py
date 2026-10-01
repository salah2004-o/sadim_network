# app/models/home_feed.py
#
# طبقة "الصفحة الرئيسية القائمة على النية" — تُعيد استخدام جداول موجودة فعلاً
# (reading_history, user_favorites, books, posts, analytics_sessions) ولا تنشئ أي
# جدول جديد. الهدف: أقل تغيير ممكن يُنتج "أكمل ما بدأت" + سطر تخصيص حقيقي + حالة
# مستخدم محسوبة (User State)، بدل الاكتفاء بصفحة رئيسية ثابتة كما كانت.
#
# قرار متعمّد: Analytics (analytics_events/analytics_sessions) وUser State وMemory
# (ai_user_knowledge) تبقى كيانات منفصلة كما هي، وهذه الوحدة فقط "تقرأ" منها لغرض
# عرض الصفحة الرئيسية — لا تُدخل عليها أي تعديل بنيوي.

from app.db.sadim_db import get_db_connection
import psycopg2.extras


def get_resume_items(user_id, limit=3):
    """آخر عناصر 'قيد القراءة' فعلياً للمستخدم (كتب/منشورات) — من reading_history
    الموجود أصلاً. لا current_page متاح اليوم (الحقل غير موجود بالجدول)، لذا الاستئناف
    حالياً هو "ارجع لنفس الكتاب/المنشور"، وليس "ارجع لنفس الصفحة" — هذا محدود بالبنية
    الحالية عن قصد، بدل الوعد بميزة (صفحة دقيقة) غير مبنية فعلياً بعد."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT h.content_type,
                   COALESCE(h.book_id, h.article_id) AS content_id,
                   COALESCE(b.title, p.title) AS title,
                   h.last_page,
                   h.last_updated
            FROM reading_history h
            LEFT JOIN books b ON b.id = h.book_id
            LEFT JOIN posts p ON p.id = h.article_id
            WHERE h.user_id = %s AND h.status = 'reading'
            ORDER BY h.last_updated DESC
            LIMIT %s
        """, (user_id, limit))
        return [dict(row) for row in cur.fetchall() if row.get('title')]
    finally:
        cur.close()
        conn.close()


def get_signal_summary(user_id):
    """أرقام حقيقية فقط (لا نص تسويقي مصطنع) لبناء جملة تخصيص من نوع
    "أنت قرأت N رواية من مكتبتنا، بقي لك M" — البند 9 من البريف."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM books")
        total_books = cur.fetchone()[0]

        cur.execute(
            "SELECT COUNT(*) FROM reading_history WHERE user_id = %s AND content_type = 'book' AND status = 'finished'",
            (user_id,)
        )
        finished_books = cur.fetchone()[0]

        cur.execute(
            "SELECT COUNT(*) FROM user_favorites WHERE user_id = %s",
            (user_id,)
        )
        favorites_count = cur.fetchone()[0]

        return {
            "total_books": total_books,
            "finished_books": finished_books,
            "remaining_books": max(total_books - finished_books, 0),
            "favorites_count": favorites_count,
        }
    finally:
        cur.close()
        conn.close()


def get_user_state(user_id, session_id=None):
    """حالة مستخدم محسوبة (deterministic، بلا AI) من analytics_sessions الموجود فعلاً
    — بدون أي تخزين جديد (تُحسب وقت الطلب). عمداً بسيطة الآن (عتبات ثابتة) وقابلة
    للتعديل لاحقاً دون أي migration، طبقاً لقرار: 'Analytics وUser State كيانات
    مختلفة ولا نخلط بينها' — هذه الدالة تقرأ من Analytics لكن الناتج (الحالة) لا
    يُخزَّن هناك ولا في أي جدول جديد.

    القيم: anonymous | new_user | returning_user | active_user
    """
    if not user_id:
        return "anonymous"

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM analytics_sessions WHERE user_id = %s", (user_id,))
        session_count = cur.fetchone()[0]
    finally:
        cur.close()
        conn.close()

    if session_count <= 1:
        return "new_user"
    if session_count <= 4:
        return "returning_user"
    return "active_user"
