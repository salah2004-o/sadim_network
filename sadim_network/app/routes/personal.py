from flask import Blueprint, jsonify, request, session

from app.db.sadim_db import get_db_connection
from app.utlis.login_required import login_required

personal_bp = Blueprint('personal', __name__, url_prefix='/api/personal')


def _content_columns(content_type):
    if content_type == 'book':
        return 'book_id', 'books', 'id'
    if content_type == 'article':
        return 'article_id', 'posts', 'id'
    raise ValueError('invalid_content_type')


@personal_bp.route('/favorite', methods=['POST', 'DELETE'])
@login_required
def favorite():
    data = request.get_json(silent=True) or {}
    content_type = data.get('content_type')
    content_id = data.get('content_id')
    try:
        key, table, column = _content_columns(content_type)
        content_id = int(content_id)
    except (ValueError, TypeError):
        return jsonify({'error': 'invalid_content'}), 400
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        if request.method == 'POST':
                cur.execute(f"INSERT INTO user_favorites (user_id, content_type, {key}) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", (session['user_id'], content_type, content_id))
        else:
            cur.execute(f"DELETE FROM user_favorites WHERE user_id = %s AND content_type = %s AND {key} = %s", (session['user_id'], content_type, content_id))
        conn.commit()
        return jsonify({'saved': request.method == 'POST'})
    finally:
        conn.close()


@personal_bp.route('/reading', methods=['POST'])
@login_required
def reading():
    data = request.get_json(silent=True) or {}
    content_type, status = data.get('content_type'), data.get('status', 'reading')
    try:
        key, _, _ = _content_columns(content_type)
        content_id = int(data.get('content_id'))
        if status not in ('reading', 'finished'):
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({'error': 'invalid_content'}), 400
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"INSERT INTO reading_history (user_id, content_type, {key}, status) VALUES (%s, %s, %s, %s) ON CONFLICT DO UPDATE SET status = EXCLUDED.status, last_updated = NOW()", (session['user_id'], content_type, content_id, status))
        conn.commit()
        return jsonify({'status': status})
    finally:
        conn.close()