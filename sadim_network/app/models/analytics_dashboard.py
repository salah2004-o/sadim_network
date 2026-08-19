"""استعلامات لوحة Analytics — كل دالة تُرجع رقماً أو قائمة حقيقية من analytics_events/analytics_sessions/users.
لا بيانات وهمية: لو مافيه صفوف بالمدى الزمني المطلوب، النتيجة صفر أو قائمة فاضية، لا تخمين."""

from app.db.sadim_db import get_db_connection

RANGE_INTERVALS = {
    "today": "1 day",
    "7d": "7 days",
    "30d": "30 days",
}


def get_dashboard_stats(range_key="7d"):
    interval = RANGE_INTERVALS.get(range_key)  # None => بلا حد زمني (كل البيانات)

    conn = get_db_connection()
    cur = conn.cursor()

    def since_clause(column, extra_and=""):
        if interval:
            return f"WHERE {column} >= NOW() - INTERVAL '{interval}' {extra_and}"
        return f"WHERE 1=1 {extra_and}"

    stats = {}

    # ---------- Users ----------
    cur.execute("SELECT COUNT(*) FROM users")
    stats["registered_users"] = cur.fetchone()[0]

    cur.execute(f"SELECT COUNT(*) FROM users {since_clause('created_at')}")
    stats["new_users"] = cur.fetchone()[0]

    cur.execute(f"""
        SELECT COUNT(DISTINCT user_id) FROM analytics_events
        {since_clause('occurred_at', "AND event_type = 'auth.login.success'")}
    """)
    stats["logged_in_users"] = cur.fetchone()[0]

    cur.execute(f"""
        SELECT COUNT(DISTINCT user_id) FROM analytics_sessions
        {since_clause('last_seen_at', "AND user_id IS NOT NULL")}
    """)
    stats["active_users"] = cur.fetchone()[0]

    cur.execute(f"""
        SELECT COUNT(*) FROM (
            SELECT user_id FROM analytics_sessions
            {since_clause('started_at', "AND user_id IS NOT NULL")}
            GROUP BY user_id HAVING COUNT(DISTINCT DATE(started_at)) > 1
        ) t
    """)
    stats["returning_users"] = cur.fetchone()[0]

    # ---------- Visitors ----------
    cur.execute(f"SELECT COUNT(*) FROM analytics_sessions {since_clause('started_at')}")
    stats["unique_sessions"] = cur.fetchone()[0]

    cur.execute(f"""
        SELECT COUNT(*) FROM analytics_sessions
        {since_clause('started_at', "AND user_id IS NULL")}
    """)
    stats["anonymous_sessions"] = cur.fetchone()[0]

    cur.execute(f"""
        SELECT COUNT(DISTINCT user_id) FROM analytics_sessions
        {since_clause('started_at', "AND user_id IS NOT NULL")}
    """)
    stats["authenticated_visitors"] = cur.fetchone()[0]

    # ---------- Engagement ----------
    cur.execute(f"SELECT COALESCE(SUM(pages_viewed),0), COALESCE(AVG(pages_viewed),0), COALESCE(AVG(events_count),0) FROM analytics_sessions {since_clause('started_at')}")
    page_views, avg_pages, avg_events = cur.fetchone()
    stats["page_views"] = page_views
    stats["avg_pages_per_session"] = round(float(avg_pages), 1)
    stats["avg_events_per_session"] = round(float(avg_events), 1)

    cur.execute(f"""
        SELECT COALESCE(AVG(EXTRACT(EPOCH FROM (last_seen_at - started_at))),0)
        FROM analytics_sessions {since_clause('started_at')}
    """)
    avg_seconds = float(cur.fetchone()[0])
    stats["avg_session_duration_seconds"] = round(avg_seconds)

    # ---------- Library ----------
    cur.execute(f"""SELECT COUNT(*) FROM analytics_events {since_clause('occurred_at', "AND event_type = 'library.view'")}""")
    stats["library_views"] = cur.fetchone()[0]

    cur.execute(f"""SELECT COUNT(*) FROM analytics_events {since_clause('occurred_at', "AND event_type = 'book.view'")}""")
    stats["book_views"] = cur.fetchone()[0]

    cur.execute(f"""SELECT COUNT(*) FROM analytics_events {since_clause('occurred_at', "AND event_type = 'download.success'")}""")
    stats["downloads"] = cur.fetchone()[0]

    cur.execute(f"""
        SELECT COUNT(DISTINCT COALESCE(user_id::text, session_id, ip))
        FROM analytics_events {since_clause('occurred_at', "AND event_type = 'download.success'")}
    """)
    stats["unique_downloaders"] = cur.fetchone()[0]

    cur.execute(f"""
        SELECT metadata->>'title' AS title, COUNT(*) AS c
        FROM analytics_events
        {since_clause('occurred_at', "AND event_type = 'download.success' AND metadata->>'title' IS NOT NULL")}
        GROUP BY metadata->>'title' ORDER BY c DESC LIMIT 5
    """)
    stats["top_books"] = [{"title": r[0], "downloads": r[1]} for r in cur.fetchall()]

    # ---------- Authentication ----------
    cur.execute(f"""SELECT COUNT(*) FROM analytics_events {since_clause('occurred_at', "AND event_type = 'auth.login.success'")}""")
    successful_logins = cur.fetchone()[0]
    cur.execute(f"""SELECT COUNT(*) FROM analytics_events {since_clause('occurred_at', "AND event_type = 'auth.login.failed'")}""")
    failed_logins = cur.fetchone()[0]
    cur.execute(f"""SELECT COUNT(*) FROM analytics_events {since_clause('occurred_at', "AND event_type = 'auth.logout'")}""")
    logouts = cur.fetchone()[0]

    stats["successful_logins"] = successful_logins
    stats["failed_logins"] = failed_logins
    stats["logouts"] = logouts
    total_attempts = successful_logins + failed_logins
    stats["login_conversion_pct"] = round((successful_logins / total_attempts) * 100, 1) if total_attempts else None

    # ---------- Traffic (visitor_type من الجلسات — تصنيف على مستوى الزائر لا الطلب) ----------
    cur.execute(f"""
        SELECT visitor_type, COUNT(*) FROM analytics_sessions
        {since_clause('started_at')} GROUP BY visitor_type
    """)
    traffic = {"human": 0, "bot": 0, "crawler": 0, "scanner": 0, "unknown": 0}
    for vtype, count in cur.fetchall():
        traffic[vtype or "unknown"] = count
    stats["traffic"] = traffic

    # ---------- Devices ----------
    cur.execute(f"""
        SELECT device_type, COUNT(*) FROM analytics_sessions
        {since_clause('started_at')} GROUP BY device_type
    """)
    devices = {"mobile": 0, "desktop": 0, "tablet": 0, "bot": 0, "unknown": 0}
    for dtype, count in cur.fetchall():
        devices[dtype or "unknown"] = devices.get(dtype or "unknown", 0) + count
    stats["devices"] = devices

    # ---------- Sources ----------
    cur.execute(f"""
        SELECT
            CASE
                WHEN referrer IS NULL OR referrer = '' THEN 'direct'
                WHEN referrer ILIKE '%%google.%%' THEN 'google'
                WHEN referrer ILIKE '%%t.me%%' OR referrer ILIKE '%%telegram%%' THEN 'telegram'
                WHEN referrer ILIKE '%%instagram%%' THEN 'instagram'
                ELSE 'other'
            END AS source,
            COUNT(*)
        FROM analytics_sessions
        {since_clause('started_at')}
        GROUP BY source
    """)
    sources = {"direct": 0, "google": 0, "telegram": 0, "instagram": 0, "other": 0}
    for source, count in cur.fetchall():
        sources[source] = count
    stats["sources"] = sources

    cur.close()
    conn.close()
    return stats


def get_top_book_this_week():
    """الكتاب الأكثر تحميلاً بآخر 7 أيام — لعرضه بالرئيسية. None لو ما فيه أي تحميل بهذي المدة (بدون بيانات وهمية)."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT metadata->>'title' AS title, metadata->>'book_id' AS book_id, COUNT(*) AS c
        FROM analytics_events
        WHERE occurred_at >= NOW() - INTERVAL '7 days'
          AND event_type = 'download.success' AND metadata->>'title' IS NOT NULL
        GROUP BY metadata->>'title', metadata->>'book_id'
        ORDER BY c DESC LIMIT 1
    """)
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return None
    title, book_id, count = row
    return {"title": title, "book_id": int(book_id) if book_id else None, "downloads": count}
