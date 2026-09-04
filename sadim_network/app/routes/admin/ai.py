import json
from flask import render_template, request, session
from app.db.sadim_db import get_db_connection
from app.routes.admin.admin import admin_bp
from app.utlis.login_required import login_required
from app.utlis.permissions import admin_required


@admin_bp.route('/ai-conversations')
@login_required
@admin_required
def ai_conversations():
    query = request.args.get('q', '').strip()
    status = request.args.get('status', '').strip()
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        pattern = f'%{query}%'
        cur.execute("""SELECT c.id, c.title, c.created_at, c.updated_at, u.id, u.username, u.name, c.status,
                       COUNT(m.id) AS message_count, COALESCE(SUM(us.input_tokens + us.output_tokens), 0) AS tokens
                       FROM ai_conversations c JOIN users u ON u.id = c.user_id
                       LEFT JOIN ai_messages m ON m.conversation_id = c.id LEFT JOIN ai_usage us ON us.conversation_id = c.id
                       WHERE (%s = '' OR u.username ILIKE %s OR u.name ILIKE %s OR c.title ILIKE %s)
                       AND (%s = '' OR c.status = %s)
                       GROUP BY c.id, u.id ORDER BY c.updated_at DESC LIMIT 100""", (query, pattern, pattern, pattern, status, status))
        rows = cur.fetchall()
        return render_template('dashboard/ai_conversations.html', conversations=rows, query=query, status=status)
    finally:
        conn.close()


@admin_bp.route('/ai-conversations/<int:conversation_id>')
@login_required
@admin_required
def ai_conversation(conversation_id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT c.id, c.title, c.created_at, c.updated_at, u.id, u.username, u.name FROM ai_conversations c JOIN users u ON u.id = c.user_id WHERE c.id = %s", (conversation_id,))
        conversation = cur.fetchone()
        if not conversation:
            return render_template('dashboard/ai_conversation.html', conversation=None, messages=[]), 404
        cur.execute("INSERT INTO audit_logs (actor_user_id, action, target_type, target_id, ip, metadata) VALUES (%s, 'ai.conversation.view', 'ai_conversation', %s, %s, %s)", (session['user_id'], conversation_id, request.remote_addr, json.dumps({'user_id': conversation[4]})))
        cur.execute("SELECT role, content, created_at, model, tools_invoked FROM ai_messages WHERE conversation_id = %s ORDER BY created_at", (conversation_id,))
        messages = cur.fetchall()
        conn.commit()
        return render_template('dashboard/ai_conversation.html', conversation=conversation, messages=messages)
    finally:
        conn.close()


@admin_bp.route('/ai-users/<int:user_id>')
@login_required
@admin_required
def ai_user_profile(user_id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, username, name, email, created_at, last_login FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()
        if not user:
            return render_template('dashboard/ai_user_profile.html', user=None, conversations=[], knowledge=[], stats={}), 404
        cur.execute("SELECT id, title, created_at, updated_at FROM ai_conversations WHERE user_id = %s ORDER BY updated_at DESC", (user_id,))
        conversations = cur.fetchall()
        cur.execute("SELECT key, value, confidence, updated_at FROM ai_user_knowledge WHERE user_id = %s ORDER BY updated_at DESC", (user_id,))
        knowledge = cur.fetchall()
        cur.execute("SELECT COUNT(*), COALESCE(SUM(input_tokens), 0), COALESCE(SUM(output_tokens), 0) FROM ai_usage WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        stats = {'requests': row[0], 'input_tokens': row[1], 'output_tokens': row[2]}
        cur.execute("INSERT INTO audit_logs (actor_user_id, action, target_type, target_id, ip, metadata) VALUES (%s, 'ai.user_profile.view', 'user', %s, %s, %s)", (session['user_id'], user_id, request.remote_addr, json.dumps({'conversation_count': len(conversations)})))
        conn.commit()
        return render_template('dashboard/ai_user_profile.html', user=user, conversations=conversations, knowledge=knowledge, stats=stats)
    finally:
        conn.close()
