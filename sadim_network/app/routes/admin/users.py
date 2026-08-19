# user

from flask import session, render_template, request, redirect, url_for, flash
from app.routes.admin.admin import admin_bp
from utlis.login_required import login_required
from utlis.permissions import admin_required
from werkzeug.utils import secure_filename
import os
from app.models.user import User
from app.db.sadim_db import get_db_connection
from app.models.analytics_model import get_user_analytics


@admin_bp.route('/userss')
@login_required
@admin_required
def admin_users_list():
    users = User.get_all()
    return render_template('dashboard/users.html', users=users)

@admin_bp.route('/view_user/<int:user_id>')
@login_required
@admin_required
def view_user(user_id):
    user = User.get_by_id(user_id)
    if user is None:
        flash('المستخدم غير موجود', 'danger')
        return redirect(url_for('admin.admin_users_list'))

    # آخر نشاط فعلي (يشمل الدخول التلقائي بعد التسجيل وGoogle، لا نموذج /login فقط)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT created_at FROM user_logs WHERE user_id = %s", (user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    last_activity = row[0] if row else None
    analytics = get_user_analytics(user_id)

    return render_template('dashboard/view_user.html', user=user, last_activity=last_activity, analytics=analytics)

@admin_bp.route('/edit_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    user = User.get_by_id(user_id)

    if not user:
        flash('المستخدم غير موجود', 'danger')
        return redirect(url_for('admin.admin_users_list'))

    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        role = request.form['role']
        status = request.form['status']
        password = request.form.get('password')
        verified = request.form.get('is_verified') == 'on'
        user.name = name
        user.email = email
        user.role = role
        user.status = status
        if password and password.strip():
            user.password_hash = password  # تأكد من أن setter الخاص بك يقوم بالتجزئة
        user.is_verified = verified
        user.update_user()

        flash('تم تحديث المستخدم بنجاح', 'success')
        return redirect(url_for('admin.admin_users_list'))

    return render_template('dashboard/edit_user.html', user=user)

@admin_bp.route('/soft_delete_user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def soft_delete_user(user_id):
    user = User.delete(user_id)
    flash('تم تعطيل المستخدم', 'warning')
    return redirect(url_for('admin.admin_users_list'))


@admin_bp.route('/add_user', methods=['GET', 'POST'])
@login_required
@admin_required
def add_user():
    if request.method == 'POST':
        name = request.form['name']
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        verified = request.form.get('is_verified') == 'on'

        user = User(name=name, username=username, email=email, password=password, role=role, is_verified=verified)
        user.add_to_db()

        flash('تم إضافة المستخدم بنجاح', 'success')
        return redirect(url_for('admin.admin_users_list'))

    return render_template('dashboard/add_user.html')
