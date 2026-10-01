from flask import Blueprint, jsonify, render_template, request, session, g

from app.db.sadim_db import get_db_connection
from app.models.ai_service import (
    MAX_MESSAGE_LENGTH,
    chat,
    get_article,
    get_book,
    guest_chat,
    summarize_content,
    validate_upload,
)
from app.models.ai_providers import list_available_providers as providers_status
from app.models.ai_quota import AIQuota
from app.models.analytics_model import log_event
from app.models.library_mdl import Library
from app.utlis.login_required import login_required
from app.limiter import limiter

ai_bp = Blueprint('ai', __name__, url_prefix='/ai')

GUEST_SESSION_KEY = 'sadeem_ai_guest_messages'
GUEST_VISITOR_ID_KEY = 'sadeem_ai_visitor_id'
GUEST_CONVERSATION_ID_KEY = 'sadeem_ai_guest_conversation_id'


def _get_visitor_id():
    """معرّف ثابت للزائر عبر نفس آلية session المستخدمة أصلاً لحفظ رسائل الزائر المؤقتة
    (GUEST_SESSION_KEY) — لا يرتبط بأي هوية حقيقية (لا بريد، لا اسم، لا IP)، ويبقى
    مجهول الهوية تماماً حتى لو تسجّل الزائر لاحقاً (لا ربط تلقائي بين الزائر والحساب الجديد)."""
    if not session.get(GUEST_VISITOR_ID_KEY):
        import secrets
        session[GUEST_VISITOR_ID_KEY] = secrets.token_urlsafe(24)
        session.permanent = True
        session.modified = True
    return session[GUEST_VISITOR_ID_KEY]


def _get_or_create_guest_conversation(visitor_id):
    """يعيد نفس محادثة الزائر المفتوحة حالياً (مخزّنة بمعرّف الجلسة)، أو ينشئ واحدة جديدة
    في نفس جدول ai_conversations الموجود (user_id=NULL, visitor_id=X) — لا جدول موازٍ."""
    conversation_id = session.get(GUEST_CONVERSATION_ID_KEY)
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        if conversation_id:
            cur.execute("SELECT id FROM ai_conversations WHERE id = %s AND visitor_id = %s", (conversation_id, visitor_id))
            if cur.fetchone():
                return conversation_id
        cur.execute(
            "INSERT INTO ai_conversations (user_id, visitor_id, title) VALUES (NULL, %s, %s) RETURNING id",
            (visitor_id, 'محادثة زائر'),
        )
        new_id = cur.fetchone()[0]
        conn.commit()
        session[GUEST_CONVERSATION_ID_KEY] = new_id
        session.modified = True
        return new_id
    finally:
        conn.close()


def _persist_guest_message(conversation_id, role, content):
    """يخزّن رسالة زائر واحدة في ai_messages الموجود أصلاً — فشل الحفظ لا يكسر استجابة الزائر
    الفعلية أبداً (المحادثة تبقى في session كاحتياطي مهما حدث بقاعدة البيانات)."""
    try:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO ai_messages (conversation_id, role, content) VALUES (%s, %s, %s)", (conversation_id, role, content))
            cur.execute("UPDATE ai_conversations SET updated_at = NOW() WHERE id = %s", (conversation_id,))
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        print('Failed to persist guest AI message:', e)


def _log_ai_event(event_type, metadata=None):
    """تسجيل حدث AI في analytics_events — بنفس نمط _log_article_event/_log_lib_event
    الموجود فعلاً ببقية المشروع. لا يخزّن نص الرسائل هنا (مخزّن أصلاً
    بجدول ai_messages لغرض وظيفي مختلف)، حتى لا تتكرر بيانات حساسة في analytics.
    فشل التسجيل لا يكسر استجابة AI الفعلية أبداً."""
    try:
        log_event(
            event_type,
            user_id=session.get('user_id'),
            session_id=g.get('sd_session_id'),
            ip=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
            path=request.path,
            visitor_type=g.get('sd_visitor_type', 'unknown'),
            metadata=metadata,
        )
    except Exception as e:
        print(f"Failed to log analytics event '{event_type}':", e)


def _conversation(conversation_id, user_id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, title FROM ai_conversations WHERE id = %s AND user_id = %s", (conversation_id, user_id))
        return cur.fetchone()
    finally:
        conn.close()


def _parse_page_context(data):
    page_context = data.get('page_context', '')
    if isinstance(page_context, dict):
        context_type = page_context.get('type')
        context_id = page_context.get('id')
        if context_type == 'book' and context_id:
            return {'type': 'book', 'id': int(context_id), 'record': get_book(int(context_id))}
        if context_type == 'article' and context_id:
            return {'type': 'article', 'id': int(context_id), 'record': get_article(int(context_id))}
        return ''
    return page_context


def _collect_attachments():
    attachments = []
    files = request.files.getlist('files') or request.files.getlist('file')
    for fs in files:
        if not fs or not fs.filename:
            continue
        attachments.append(validate_upload(fs))
    return attachments


@ai_bp.route('/')
def index():
    """Logged-in users get full chat; guests get ephemeral session chat."""
    context_type = request.args.get('context_type', '')
    context_id = request.args.get('context_id', type=int)
    page_context = None
    if context_type == 'book' and context_id:
        page_context = {'type': 'book', 'id': context_id, 'record': get_book(context_id)}
    elif context_type == 'article' and context_id:
        page_context = {'type': 'article', 'id': context_id, 'record': get_article(context_id)}
    is_guest = not session.get('user_id')
    return render_template(
        'ai/index.html',
        initial_context=page_context or {},
        is_guest=is_guest,
        providers=providers_status(),
    )


@ai_bp.route('/providers')
def providers():
    return jsonify(providers_status())


@ai_bp.route('/conversations')
@login_required
def conversations():
    page = max(request.args.get('page', 1, type=int), 1)
    limit, offset = 20, (page - 1) * 20
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, title, created_at, updated_at FROM ai_conversations WHERE user_id = %s ORDER BY updated_at DESC LIMIT %s OFFSET %s", (session['user_id'], limit, offset))
        return jsonify([dict(zip(('id', 'title', 'created_at', 'updated_at'), row)) for row in cur.fetchall()])
    finally:
        conn.close()


@ai_bp.route('/conversations', methods=['POST'])
@login_required
def new_conversation():
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO ai_conversations (user_id, title) VALUES (%s, %s) RETURNING id", (session['user_id'], 'محادثة جديدة'))
        conversation_id = cur.fetchone()[0]
        conn.commit()
        _log_ai_event('ai_chat_started', metadata={'conversation_id': conversation_id})
        return jsonify({'id': conversation_id, 'title': 'محادثة جديدة'})
    finally:
        conn.close()


@ai_bp.route('/conversations/<int:conversation_id>')
@login_required
def conversation(conversation_id):
    if not _conversation(conversation_id, session['user_id']):
        return jsonify({'error': 'not_found'}), 404
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, role, content, created_at, model, tools_invoked FROM ai_messages WHERE conversation_id = %s ORDER BY created_at ASC", (conversation_id,))
        return jsonify([dict(zip(('id', 'role', 'content', 'created_at', 'model', 'tools_invoked'), row)) for row in cur.fetchall()])
    finally:
        conn.close()


@ai_bp.route('/conversations/<int:conversation_id>', methods=['DELETE'])
@login_required
def delete_conversation(conversation_id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM ai_conversations WHERE id = %s AND user_id = %s", (conversation_id, session['user_id']))
        conn.commit()
        return ('', 204) if cur.rowcount else (jsonify({'error': 'not_found'}), 404)
    finally:
        conn.close()


@ai_bp.route('/conversations/<int:conversation_id>/messages', methods=['POST'])
@login_required
@limiter.limit("20 per day; 5 per minute", key_func=lambda: str(session.get('user_id', 'anonymous')))
def send_message(conversation_id):
    if not _conversation(conversation_id, session['user_id']):
        return jsonify({'error': 'not_found'}), 404

    preferred = None
    attachments = []
    try:
        if request.content_type and 'multipart/form-data' in request.content_type:
            message = str(request.form.get('message', '')).strip()
            preferred = (request.form.get('provider') or '').strip() or None
            raw_ctx = request.form.get('page_context', '')
            try:
                import json as _json
                data = {'page_context': _json.loads(raw_ctx) if raw_ctx else ''}
            except Exception:
                data = {'page_context': raw_ctx}
            attachments = _collect_attachments()
        else:
            data = request.get_json(silent=True) or {}
            message = str(data.get('message', '')).strip()
            preferred = (data.get('provider') or '').strip() or None
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    if not message and not attachments:
        return jsonify({'error': 'empty_message'}), 400
    if not message:
        message = 'حلّل المرفق من فضلك.'
    if len(message) > MAX_MESSAGE_LENGTH:
        return jsonify({'error': 'message_too_long', 'max_length': MAX_MESSAGE_LENGTH}), 400
    allowed, quota_info = AIQuota.check_quota(session['user_id'], 'daily_chat_messages')
    if not allowed:
        return jsonify({'error': 'daily_limit', 'quota': quota_info}), 429
    try:
        page_context = _parse_page_context(data)
        if not page_context:
            page_context = 'تخصيص المستخدم: ' + str(__import__('app.models.ai_service', fromlist=['get_user_context']).get_user_context(session['user_id']))[:1500]
        result = chat(
            session['user_id'], conversation_id, message,
            page_context=page_context,
            attachments=attachments or None,
            preferred_provider=preferred,
        )
        _log_ai_event('ai_message_sent', metadata={
            'conversation_id': conversation_id,
            'context_type': (data.get('page_context') or {}).get('type') if isinstance(data.get('page_context'), dict) else None,
            'provider': result.get('provider'),
        })
        return jsonify(result)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 429 if str(exc) == 'daily_limit' else 400
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'ai_unavailable', 'message': str(exc)}), 503


@ai_bp.route('/guest/messages', methods=['GET'])
def guest_messages():
    return jsonify(session.get(GUEST_SESSION_KEY, []))


@ai_bp.route('/guest/messages', methods=['DELETE'])
def clear_guest_messages():
    session.pop(GUEST_SESSION_KEY, None)
    session.pop(GUEST_CONVERSATION_ID_KEY, None)  # يبدأ محادثة جديدة في القاعدة لاحقاً — لا يحذف المحادثة القديمة
    session.modified = True
    return ('', 204)


@ai_bp.route('/guest/messages', methods=['POST'])
@limiter.limit("8 per day; 3 per minute", key_func=lambda: request.remote_addr or 'guest')
def guest_send_message():
    preferred = None
    attachments = []
    try:
        if request.content_type and 'multipart/form-data' in request.content_type:
            message = str(request.form.get('message', '')).strip()
            preferred = (request.form.get('provider') or '').strip() or None
            raw_ctx = request.form.get('page_context', '')
            try:
                import json as _json
                data = {'page_context': _json.loads(raw_ctx) if raw_ctx else ''}
            except Exception:
                data = {'page_context': raw_ctx}
            attachments = _collect_attachments()
        else:
            data = request.get_json(silent=True) or {}
            message = str(data.get('message', '')).strip()
            preferred = (data.get('provider') or '').strip() or None
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    if not message and not attachments:
        return jsonify({'error': 'empty_message'}), 400
    if not message:
        message = 'حلّل المرفق من فضلك.'
    if len(message) > MAX_MESSAGE_LENGTH:
        return jsonify({'error': 'message_too_long', 'max_length': MAX_MESSAGE_LENGTH}), 400

    history = list(session.get(GUEST_SESSION_KEY, []))
    try:
        page_context = _parse_page_context(data)
        result = guest_chat(history, message, page_context=page_context, attachments=attachments or None, preferred_provider=preferred)
    except ValueError as exc:
        code = 429 if str(exc) in ('guest_limit', 'daily_limit') else 400
        return jsonify({'error': str(exc)}), code
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'ai_unavailable', 'message': str(exc)}), 503

    history.append({'role': 'user', 'content': message})
    history.append({'role': 'assistant', 'content': result['content']})
    session[GUEST_SESSION_KEY] = history[-40:]
    session.modified = True

    # حفظ دائم بجانب الذاكرة المؤقتة أعلاه — لا يؤثّر على استجابة الزائر إطلاقاً إذا فشل
    visitor_id = _get_visitor_id()
    guest_conversation_id = _get_or_create_guest_conversation(visitor_id)
    _persist_guest_message(guest_conversation_id, 'user', message)
    _persist_guest_message(guest_conversation_id, 'assistant', result['content'])

    _log_ai_event('ai_message_sent', metadata={'guest': True, 'provider': result.get('provider')})
    return jsonify(result)


@ai_bp.route('/summarize', methods=['POST'])
@limiter.limit("15 per day; 4 per minute", key_func=lambda: str(session.get('user_id') or request.remote_addr or 'guest'))
def summarize():
    data = request.get_json(silent=True) or {}
    context_type = data.get('type') or data.get('context_type')
    context_id = data.get('id') or data.get('context_id')
    preferred = (data.get('provider') or '').strip() or None
    if not context_type or not context_id:
        return jsonify({'error': 'missing_context'}), 400
    try:
        context_id = int(context_id)
    except (TypeError, ValueError):
        return jsonify({'error': 'invalid_id'}), 400

    source = data.get('source') if data.get('source') in SUMMARIZE_SOURCES else None
    user_id = session.get('user_id')

    # ملخص الكتاب المخزّن يُخدم فوراً وبلا استهلاك حصة — المدخل (العنوان+الوصف) واحد لكل الزوار
    if context_type == 'book':
        cached = Library.get_ai_summary(context_id)
        if cached:
            result = {'content': cached, 'provider': 'cache', 'tools': []}
            _log_summarize_events(context_type, context_id, result, source, cached=True)
            return jsonify(result)

    if user_id:
        allowed, quota_info = AIQuota.check_quota(user_id, 'daily_summaries')
        if not allowed:
            return jsonify({'content': f"استخدمت حد التلخيص المجاني ({quota_info['limit']} {quota_info['period']}).", 'quota_exceeded': True}), 429

    if context_type == 'article':
        rows = get_article(context_id)
        if not rows:
            return jsonify({'error': 'not_found'}), 404
        record = rows[0]
        result = summarize_content(record.get('title', ''), record.get('content', ''), 'article', preferred, user_id=user_id)
    elif context_type == 'book':
        rows = get_book(context_id)
        if not rows:
            return jsonify({'error': 'not_found'}), 404
        record = rows[0]
        result = summarize_content(record.get('title', ''), record.get('desc_text', ''), 'book', preferred, user_id=user_id)
        # لا نخزّن البديل المحلي (فشل النموذج) ولا رسالة تجاوز الحصة
        if result.get('content') and result.get('provider') not in ('local', 'quota') and not result.get('quota_exceeded'):
            try:
                Library.set_ai_summary(context_id, result['content'])
            except Exception as e:
                print('Failed to cache book summary:', e)
    else:
        return jsonify({'error': 'unsupported_type'}), 400

    _log_summarize_events(context_type, context_id, result, source, cached=False)
    return jsonify(result)


SUMMARIZE_SOURCES = {'book_page'}


def _log_summarize_events(context_type, context_id, result, source, cached):
    """ai_summarize_used يبقى كما هو لكل تلخيص (source/cached مفاتيح إضافية فقط).
    ai_summarize.from_book_page حدث إضافي لتلخيص من صفحة الرواية — لا تجمع الحدثين عند عدّ استخدام AI."""
    metadata = {'context_type': context_type, 'context_id': context_id, 'provider': result.get('provider')}
    if source:
        metadata['source'] = source
    if cached:
        metadata['cached'] = True
    _log_ai_event('ai_summarize_used', metadata=metadata)
    if source == 'book_page' and context_type == 'book':
        _log_ai_event('ai_summarize.from_book_page', metadata={'book_id': context_id, 'cached': cached})
