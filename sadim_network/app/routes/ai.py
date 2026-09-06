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
from app.models.analytics_model import log_event
from app.utlis.login_required import login_required
from app.limiter import limiter

ai_bp = Blueprint('ai', __name__, url_prefix='/ai')

GUEST_SESSION_KEY = 'sadeem_ai_guest_messages'


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
    except Exception:
        return jsonify({'error': 'ai_unavailable'}), 503


@ai_bp.route('/guest/messages', methods=['GET'])
def guest_messages():
    return jsonify(session.get(GUEST_SESSION_KEY, []))


@ai_bp.route('/guest/messages', methods=['DELETE'])
def clear_guest_messages():
    session.pop(GUEST_SESSION_KEY, None)
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
    except Exception:
        return jsonify({'error': 'ai_unavailable'}), 503

    history.append({'role': 'user', 'content': message})
    history.append({'role': 'assistant', 'content': result['content']})
    session[GUEST_SESSION_KEY] = history[-40:]
    session.modified = True
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

    if context_type == 'article':
        rows = get_article(context_id)
        if not rows:
            return jsonify({'error': 'not_found'}), 404
        record = rows[0]
        result = summarize_content(record.get('title', ''), record.get('content', ''), 'article', preferred)
    elif context_type == 'book':
        rows = get_book(context_id)
        if not rows:
            return jsonify({'error': 'not_found'}), 404
        record = rows[0]
        result = summarize_content(record.get('title', ''), record.get('desc_text', ''), 'book', preferred)
    else:
        return jsonify({'error': 'unsupported_type'}), 400

    _log_ai_event('ai_summarize_used', metadata={
        'context_type': context_type, 'context_id': context_id, 'provider': result.get('provider'),
    })
    return jsonify(result)
