# ملف لادارة الموقع هذه نسخة متواضعة
#_____  
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.utils import secure_filename
#_________
from app.db.sadim_db import get_db_connection
from utlis.login_required import login_required
from utlis.permissions import admin_required
from datetime import datetime
from app.models.comments import Comments
admin_bp = Blueprint('admin', __name__, url_prefix='/dashboard', template_folder='../../templates')


# ------------------ صفحة عرض المستخدمين ------------------
@admin_bp.route('/users')
@login_required
@admin_required

def dashboard_users():
    conn = get_db_connection()
    cur = conn.cursor()

    # المتصلين الآن – آخر 5 دقائق
    cur.execute("""
        SELECT email, username, ip, user_agent, created_at 
        FROM user_logs 
        WHERE created_at >= NOW() - INTERVAL '5 minutes'
        ORDER BY created_at DESC
    """)
    online_users = cur.fetchall()

    # غير المتصلين
    cur.execute("""
        SELECT email, username, ip, user_agent, created_at 
        FROM user_logs 
        WHERE created_at < NOW() - INTERVAL '5 minutes'
        ORDER BY created_at DESC
    """)
    offline_users = cur.fetchall()

    # إحصائيات آخر ظهور
    stats = {}

    cur.execute("SELECT COUNT(*) FROM user_logs WHERE created_at >= NOW() - INTERVAL '1 day'")
    stats["day"] = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM user_logs WHERE created_at >= NOW() - INTERVAL '7 days'")
    stats["week"] = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM user_logs WHERE created_at >= NOW() - INTERVAL '30 days'")
    stats["month"] = cur.fetchone()[0]

    cur.close()
    conn.close()

    return render_template(
        'dashboard/users_dashboard.html',
        online_users=online_users,
        offline_users=offline_users,
        stats=stats
    )

@admin_bp.route('/manage/comments', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_comments():
    if request.method == 'POST':
        comment_id = request.form.get('comment_id')
        user_id = session.get('user_id')
        user_role = session.get('role', 'user') # توحيد المسمى مع الـ session

        if Comments.delete_comment(comment_id, user_id, user_role):
            flash('تم حذف التعليق بنجاح', 'success')
        else:
            flash('فشل حذف التعليق أو لا تملك الصلاحية.', 'danger')

        # تأكد أن اسم الـ blueprint هنا يطابق ما عرفته في الـ __init__.py
        return redirect(url_for('admin.manage_comments')) 

    comments = Comments.get_all_comments()
    return render_template('dashboard/comments_dashboard.html', comments=comments)
from app.routes.admin import users, visits, services, library, bots_admin, articles, bot_limits
