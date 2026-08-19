import secrets
from psycopg2.extras import Json
from db.sadim_db import get_db_connection
from app.models.ua_parser import parse_user_agent

SESSION_COOKIE_NAME = "sd_sid"

# أحداث تتطلب user_id إلزامياً (أحداث مصادقة ناجحة فقط — auth.login.failed يبقى بدون user_id لأننا لا نعرف هوية صاحب المحاولة)
REQUIRES_USER_ID = {
    "auth.login.success",
    "auth.logout",
    "auth.register",
    "auth.session_created",
    "referral.success",
}

# مفاتيح تُحذف من metadata قبل التخزين مهما كان مصدر الاستدعاء — لا كلمات مرور ولا tokens داخل Analytics إطلاقاً
_SENSITIVE_KEY_MARKERS = ("password", "token", "authorization", "cookie", "secret")


def _sanitize_metadata(data):
    """يشيل أي مفتاح فيه إشارة لبيانات حساسة (password/token/authorization/cookie/secret)، بشكل متكرر لأي dict متداخل."""
    if not isinstance(data, dict):
        return {}
    clean = {}
    for key, value in data.items():
        key_lower = str(key).lower()
        if any(marker in key_lower for marker in _SENSITIVE_KEY_MARKERS):
            continue
        clean[key] = _sanitize_metadata(value) if isinstance(value, dict) else value
    return clean


def log_event(event_type, user_id=None, session_id=None, ip=None, user_agent=None,
              path=None, referrer=None, visitor_type="unknown", metadata=None):
    """نقطة الدخول الوحيدة لتسجيل أي حدث Analytics — بدل INSERT مباشر متفرق بكل route.
    يرفض تسجيل حدث بدون event_type، ويرفض أحداث المصادقة الناجحة بدون user_id."""
    if not event_type:
        raise ValueError("log_event: event_type مطلوب")
    if event_type in REQUIRES_USER_ID and not user_id:
        raise ValueError(f"log_event: الحدث '{event_type}' يتطلب user_id")

    clean_metadata = _sanitize_metadata(metadata or {})

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO analytics_events
                (event_type, user_id, session_id, ip, user_agent, path, referrer, visitor_type, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, occurred_at
            """,
            (event_type, user_id, session_id, ip, user_agent, path, referrer, visitor_type, Json(clean_metadata)),
        )
        row = cur.fetchone()
        conn.commit()
        return {"id": row[0], "occurred_at": row[1]}
    finally:
        cur.close()
        conn.close()


def generate_session_id():
    """token عشوائي آمن — لا يحمل أي معنى قابل لتحديد الهوية بذاته (لا IP، لا بريد، لا user_id)."""
    return secrets.token_urlsafe(32)


def touch_session(session_id, user_id=None, ip=None, user_agent=None, referrer=None,
                   landing_page=None, count_pageview=True, visitor_type="unknown"):
    """ينشئ صف الجلسة لو أول ظهور له، أو يحدّثه لو موجود (UPSERT ذرّي بطلب واحد).
    referrer/landing_page تُسجَّل فقط عند الإنشاء الأول (نقطة الدخول الحقيقية للجلسة) — لا تُستبدل لاحقاً.
    count_pageview=False تُستخدم لتحديث last_seen_at بدون احتساب مشاهدة (زيارة لمسار إداري مثلاً).
    visitor_type القادم من bot_classifier.classify_visitor() — تسجيل الدخول الفعلي يبقى الإشارة الأقوى (يترقّى لـ'human' دائماً)."""
    ua_info = parse_user_agent(user_agent)
    if user_id:
        visitor_type = "human"
    initial_count = 1 if count_pageview else 0

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO analytics_sessions
                (session_id, user_id, visitor_type, ip, user_agent, device_type, browser, os,
                 referrer, landing_page, pages_viewed, events_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (session_id) DO UPDATE SET
                last_seen_at = NOW(),
                user_id = COALESCE(EXCLUDED.user_id, analytics_sessions.user_id),
                visitor_type = CASE
                    WHEN EXCLUDED.user_id IS NOT NULL THEN 'human'
                    ELSE analytics_sessions.visitor_type
                END,
                pages_viewed = analytics_sessions.pages_viewed + %s,
                events_count = analytics_sessions.events_count + %s
            """,
            (
                session_id, user_id, visitor_type, ip, user_agent,
                ua_info["device_type"], ua_info["browser"], ua_info["os"],
                referrer, landing_page, initial_count, initial_count,
                initial_count, initial_count,
            ),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def end_session(session_id):
    """يُستدعى عند حدث خروج صريح (auth.logout) — تمييز واضح بين جلسة انتهت فعلاً وجلسة راكدة فقط."""
    if not session_id:
        return
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE analytics_sessions SET ended_at = NOW() WHERE session_id = %s AND ended_at IS NULL",
            (session_id,),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


# تسميات عربية مختصرة لكل نوع حدث — تُستخدم بـTimeline ملف المستخدم فقط، لا تؤثر على التخزين
EVENT_LABELS = {
    "auth.login.success": "تسجيل دخول",
    "auth.login.failed": "محاولة دخول فاشلة",
    "auth.logout": "تسجيل خروج",
    "auth.register": "إنشاء حساب",
    "library.view": "تصفّح قائمة المكتبة",
    "book.view": "مشاهدة رواية",
    "book.search": "بحث بالمكتبة",
    "download.success": "تحميل ناجح",
    "download.failed": "تحميل فاشل",
    "article.view": "مشاهدة مقال",
    "referral.success": "انضمّ عبر دعوتك",
}


def get_user_analytics(user_id, timeline_limit=30):
    """كل إحصائيات مستخدم واحد لصفحة ملفه بلوحة الإدارة — أرقام حقيقية فقط، صفر افتراض."""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM analytics_events WHERE user_id = %s AND event_type = 'auth.login.success'", (user_id,))
    login_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM analytics_sessions WHERE user_id = %s", (user_id,))
    session_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM analytics_events WHERE user_id = %s", (user_id,))
    total_events = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(DISTINCT metadata->>'book_id') FROM analytics_events
        WHERE user_id = %s AND event_type = 'book.view'
    """, (user_id,))
    books_viewed = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(DISTINCT metadata->>'book_id') FROM analytics_events
        WHERE user_id = %s AND event_type = 'download.success'
    """, (user_id,))
    books_downloaded = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(DISTINCT metadata->>'post_id') FROM analytics_events
        WHERE user_id = %s AND event_type = 'article.view'
    """, (user_id,))
    articles_viewed = cur.fetchone()[0]

    cur.execute("""
        SELECT DISTINCT device_type FROM analytics_sessions
        WHERE user_id = %s AND device_type IS NOT NULL
    """, (user_id,))
    devices = [r[0] for r in cur.fetchall()]

    cur.execute("""
        SELECT ip, user_agent FROM analytics_events
        WHERE user_id = %s ORDER BY occurred_at DESC LIMIT 1
    """, (user_id,))
    last_row = cur.fetchone()
    last_ip, last_user_agent = last_row if last_row else (None, None)

    cur.execute("""
        SELECT event_type, occurred_at, metadata FROM analytics_events
        WHERE user_id = %s ORDER BY occurred_at DESC LIMIT %s
    """, (user_id, timeline_limit))
    timeline = []
    for event_type, occurred_at, metadata in cur.fetchall():
        label = EVENT_LABELS.get(event_type, event_type)
        detail = ""
        if metadata:
            detail = metadata.get("title") or metadata.get("query") or ""
        timeline.append({
            "occurred_at": occurred_at,
            "event_type": event_type,
            "label": label,
            "detail": detail,
        })

    cur.close()
    conn.close()

    return {
        "login_count": login_count,
        "session_count": session_count,
        "total_events": total_events,
        "books_viewed": books_viewed,
        "books_downloaded": books_downloaded,
        "articles_viewed": articles_viewed,
        "devices": devices,
        "last_ip": last_ip,
        "last_user_agent": last_user_agent,
        "timeline": timeline,
    }


def audit_log(actor_user_id, action, target_type=None, target_id=None, ip=None, metadata=None):
    """سجل تدقيق منفصل تماماً عن analytics_events — نشاط الإدارة يُوثَّق هنا حصراً، لا يختلط بأي
    إحصائية "مستخدمين/زوار" عامة. نفس تنظيف metadata (password/token/...) قبل أي تخزين."""
    clean_metadata = _sanitize_metadata(metadata or {})
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO audit_logs (actor_user_id, action, target_type, target_id, ip, metadata)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (actor_user_id, action, target_type, target_id, ip, Json(clean_metadata)),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()
