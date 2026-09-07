import json
from flask import render_template, request, session, redirect, url_for, flash
from app.db.sadim_db import get_db_connection
from app.routes.admin.admin import admin_bp
from app.utlis.login_required import login_required
from app.utlis.permissions import admin_required
from app.models.ai_quota import AIQuota


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
                   COALESCE(m.message_count, 0) AS message_count, COALESCE(us.tokens, 0) AS tokens, c.visitor_id
                       FROM ai_conversations c LEFT JOIN users u ON u.id = c.user_id
                   LEFT JOIN (SELECT conversation_id, COUNT(*) AS message_count FROM ai_messages GROUP BY conversation_id) m ON m.conversation_id = c.id
                   LEFT JOIN (SELECT conversation_id, SUM(input_tokens + output_tokens) AS tokens FROM ai_usage GROUP BY conversation_id) us ON us.conversation_id = c.id
                       WHERE (%s = '' OR u.username ILIKE %s OR u.name ILIKE %s OR c.title ILIKE %s)
                       AND (%s = '' OR c.status = %s)
                       ORDER BY c.updated_at DESC LIMIT 100""", (query, pattern, pattern, pattern, status, status))
        rows = cur.fetchall()
        cur.execute("""SELECT COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE),
                   COUNT(*) FILTER (WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'),
                   COUNT(*) FILTER (WHERE status = 'success'), COUNT(*) FILTER (WHERE status = 'fallback')
                   FROM ai_conversations""")
        today, week, successful, fallback = cur.fetchone()
        total = successful + fallback
        stats = {'today': today, 'week': week, 'successful': successful, 'fallback': fallback,
             'failure_rate': round((fallback / total) * 100, 1) if total else 0}
        return render_template('dashboard/ai_conversations.html', conversations=rows, query=query, status=status, stats=stats)
    finally:
        conn.close()


@admin_bp.route('/ai-conversations/<int:conversation_id>')
@login_required
@admin_required
def ai_conversation(conversation_id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT c.id, c.title, c.created_at, c.updated_at, u.id, u.username, u.name, c.visitor_id FROM ai_conversations c LEFT JOIN users u ON u.id = c.user_id WHERE c.id = %s", (conversation_id,))
        conversation = cur.fetchone()
        if not conversation:
            return render_template('dashboard/ai_conversation.html', conversation=None, messages=[]), 404
        cur.execute("INSERT INTO audit_logs (actor_user_id, action, target_type, target_id, ip, metadata) VALUES (%s, 'ai.conversation.view', 'ai_conversation', %s, %s, %s)", (session['user_id'], conversation_id, request.remote_addr, json.dumps({'user_id': conversation[4], 'visitor_id': conversation[7]})))
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


@admin_bp.route('/ai-quotas')
@login_required
@admin_required
def ai_quotas():
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT u.id, u.username, u.name, u.email,
                   COUNT(DISTINCT aq.id) as quota_count,
                   COALESCE(SUM(CASE WHEN aq.is_unlimited THEN 0 ELSE aq.quota_limit END), 0) as total_limits,
                   COUNT(DISTINCT au.id) as usage_today
            FROM users u
            LEFT JOIN ai_quotas aq ON aq.user_id = u.id
            LEFT JOIN ai_usage au ON au.user_id = u.id AND au.created_at::date = CURRENT_DATE
            WHERE u.role != 'admin'
            GROUP BY u.id, u.username, u.name, u.email
            ORDER BY u.id DESC
            LIMIT 100
        """)
        users = cur.fetchall()
        return render_template('dashboard/ai_quotas.html', users=users)
    finally:
        conn.close()


@admin_bp.route('/ai-quotas/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def ai_quota_edit(user_id):
    from app.models.user import User
    user = User.get_by_id(user_id)
    if not user:
        flash('المستخدم غير موجود.', 'error')
        return redirect(url_for('admin.ai_quotas'))

    if request.method == 'POST':
        quota_key = request.form.get('quota_key', '').strip()
        quota_limit = request.form.get('quota_limit', type=int)
        period = request.form.get('period', 'daily').strip()
        is_unlimited = request.form.get('is_unlimited') == 'on'
        if quota_key and quota_limit is not None:
            AIQuota.set_quota(user_id, quota_key, quota_limit, period, is_unlimited)
            flash('تم تحديث الحد.', 'success')
        return redirect(url_for('admin.ai_quota_edit', user_id=user_id))

    quotas = AIQuota.get_user_quotas(user_id)
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT event_type, COUNT(*), COALESCE(SUM(input_tokens), 0), COALESCE(SUM(output_tokens), 0)
            FROM ai_usage WHERE user_id = %s AND created_at::date = CURRENT_DATE
            GROUP BY event_type
        """, (user_id,))
        usage_today = cur.fetchall()
    finally:
        conn.close()

    return render_template('dashboard/ai_quota_edit.html', user=user, quotas=quotas, usage_today=usage_today)
