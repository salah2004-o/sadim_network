from urllib.parse import urlparse

from flask import Blueprint, jsonify, request, session, g

from app.limiter import limiter
from app.models.analytics_model import log_event

events_bp = Blueprint('events', __name__)

# أحداث الواجهة (JS) المسموحة فقط — أي اسم خارج هذه القائمة يُرفض، حتى لا يصير المسار
# بوابة مفتوحة لكتابة أي event_type في analytics_events. أحداث الخادم لا تمر من هنا إطلاقاً.
CLIENT_EVENTS = {
    "book.read.progress",
    "signup.prompt.shown",
    "signup.prompt.clicked",
    "share.clicked",
    "search.result.clicked",
}

_MAX_KEYS = 12
_MAX_STR = 200


def _clean_metadata(raw):
    """metadata مسطّحة فقط (نص/رقم/منطقي) بحد أقصى للمفاتيح والطول — بيانات الواجهة غير موثوقة."""
    if not isinstance(raw, dict):
        return {}
    clean = {}
    for key, value in list(raw.items())[:_MAX_KEYS]:
        key = str(key)[:40]
        if isinstance(value, bool) or value is None:
            clean[key] = value
        elif isinstance(value, (int, float)):
            clean[key] = value
        elif isinstance(value, str):
            clean[key] = value[:_MAX_STR]
    return clean


def _page_path(data):
    """مسار الصفحة التي أطلقت الحدث (لا /api/events نفسه)."""
    path = data.get('path')
    if not isinstance(path, str) or not path.startswith('/'):
        path = urlparse(request.referrer or '').path or None
    return path[:255] if path else None


@events_bp.route('/api/events', methods=['POST'])
@limiter.limit("40 per minute; 600 per hour", key_func=lambda: request.cookies.get('sd_sid') or request.remote_addr or 'anon')
def client_event():
    # sendBeacon يرسل Blob بنوع application/json، وبعض المتصفحات ترسله text/plain — نقبل الاثنين
    data = request.get_json(force=True, silent=True) or {}
    event_type = data.get('event')
    if event_type not in CLIENT_EVENTS:
        return jsonify({'error': 'unknown_event'}), 400
    try:
        log_event(
            event_type,
            user_id=session.get('user_id'),
            session_id=g.get('sd_session_id'),
            ip=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
            path=_page_path(data),
            visitor_type=g.get('sd_visitor_type', 'unknown'),
            metadata=_clean_metadata(data.get('metadata')),
        )
    except Exception as e:
        print(f"Failed to log analytics event '{event_type}':", e)
    return ('', 204)
