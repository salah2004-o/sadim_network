# مراقبة المنشورات من لوحة تحكم الأدمن (حذف بعدي لأي منشور مخالف)
from flask import render_template, request, redirect, url_for, session, flash
from app.routes.admin.admin import admin_bp
from utlis.login_required import login_required
from utlis.permissions import admin_required
from app.models.post_model import Post


@admin_bp.route('/manage/articles', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_articles():
    if request.method == 'POST':
        post_id = request.form.get('post_id')
        if Post.delete_post(post_id, session.get('user_id'), 'admin'):
            flash('تم حذف المنشور بنجاح', 'success')
        else:
            flash('تعذر حذف المنشور', 'danger')
        return redirect(url_for('admin.manage_articles'))

    posts = Post.get_all(limit=1000, offset=0)
    return render_template('dashboard/articles_dashboard.html', posts=posts)
