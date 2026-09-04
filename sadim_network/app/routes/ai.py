from flask import Blueprint, jsonify, render_template, request, session

from app.db.sadim_db import get_db_connection
from app.models.ai_service import MAX_MESSAGE_LENGTH, chat
from app.utlis.login_required import login_required
from app.limiter import limiter

ai_bp = Blueprint('ai', __name__, url_prefix='/ai')


def _conversation(conversation_id, user_id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, title FROM ai_conversations WHERE id = %s AND user_id = %s", (conversation_id, user_id))
        return cur.fetchone()
    finally:
        conn.close()


@ai_bp.route('/')
@login_required
def index():
    return render_template('ai/index.html')


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
    data = request.get_json(silent=True) or {}
    message = str(data.get('message', '')).strip()
    if not message:
        return jsonify({'error': 'empty_message'}), 400
    if len(message) > MAX_MESSAGE_LENGTH:
        return jsonify({'error': 'message_too_long', 'max_length': MAX_MESSAGE_LENGTH}), 400
    try:
        page_context = data.get('page_context', '')
        if not page_context:
            page_context = 'تخصيص المستخدم: ' + str(__import__('app.models.ai_service', fromlist=['get_user_context']).get_user_context(session['user_id']))[:1500]
        return jsonify(chat(session['user_id'], conversation_id, message, page_context=page_context))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 429 if str(exc) == 'daily_limit' else 400
    except Exception:
        return jsonify({'error': 'ai_unavailable'}), 503
