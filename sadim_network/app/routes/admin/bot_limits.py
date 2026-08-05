# إدارة حدود عدد البوتات لكل مستخدم — لوحة الأدمن
from datetime import datetime, timedelta
from flask import render_template, request, redirect, url_for, flash
from app.routes.admin.admin import admin_bp
from utlis.login_required import login_required
from utlis.permissions import admin_required
from app.models.bot_limit_model import BotLimitGrant
from app.db.sadim_db import get_db_connection

DURATION_PRESETS = {
    "1m": 30, "3m": 90, "6m": 180, "1y": 365,
}


def _get_all_users_light():
    """قائمة خفيفة (id/username/email بس) لقائمة اختيار المستخدم — عمداً بدون User.get_all()
    لأنها تجيب كل عمود لكل مستخدم بما فيها bio عبر استعلام منفصل لكل صف (N+1)، وهذا بطيء
    جداً لصفحة بس تحتاج تعرض أسماء المستخدمين بقائمة اختيار."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, username, email FROM users ORDER BY username")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{"id": r[0], "username": r[1], "email": r[2]} for r in rows]


def _compute_expires_at(duration_preset, custom_date):
    """يحوّل اختيار المدة بالنموذج لتاريخ انتهاء فعلي — None يعني بلا انتهاء (دائم)."""
    if duration_preset == "custom" and custom_date:
        try:
            return datetime.strptime(custom_date, "%Y-%m-%d")
        except ValueError:
            return None
    days = DURATION_PRESETS.get(duration_preset)
    return datetime.now() + timedelta(days=days) if days else None


@admin_bp.route('/bot-limits')
@login_required
@admin_required
def bot_limits_list():
    grants = BotLimitGrant.get_all_with_stats()
    users = _get_all_users_light()
    return render_template('dashboard/bot_limits.html', grants=grants, users=users, default_limit=1)


def _apply_grant_from_form(user_id):
    is_unlimited = request.form.get('is_unlimited') == 'on'
    bot_limit_raw = request.form.get('bot_limit', '').strip()
    duration_preset = request.form.get('duration_preset', '')
    custom_date = request.form.get('custom_date', '')

    bot_limit = None
    if not is_unlimited:
        if not bot_limit_raw.isdigit() or int(bot_limit_raw) < 1:
            flash("يرجى إدخال حد صحيح (رقم أكبر من صفر) أو تفعيل خيار غير محدود.", "error")
            return False
        bot_limit = int(bot_limit_raw)

    expires_at = _compute_expires_at(duration_preset, custom_date)
    BotLimitGrant.upsert(user_id, bot_limit=bot_limit, is_unlimited=is_unlimited, expires_at=expires_at)
    return True


@admin_bp.route('/bot-limits/<int:user_id>/set', methods=['POST'])
@login_required
@admin_required
def bot_limits_set(user_id):
    if _apply_grant_from_form(user_id):
        flash("✅ تم تحديث حد البوتات بنجاح.", "success")
    return redirect(url_for('admin.bot_limits_list'))


@admin_bp.route('/bot-limits/grant', methods=['POST'])
@login_required
@admin_required
def bot_limits_grant_new():
    user_id_raw = request.form.get('user_id', '')
    if not user_id_raw.isdigit():
        flash("يرجى اختيار مستخدم صحيح.", "error")
        return redirect(url_for('admin.bot_limits_list'))
    if _apply_grant_from_form(int(user_id_raw)):
        flash("✅ تم منح الحد بنجاح.", "success")
    return redirect(url_for('admin.bot_limits_list'))


@admin_bp.route('/bot-limits/<int:user_id>/cancel', methods=['POST'])
@login_required
@admin_required
def bot_limits_cancel(user_id):
    BotLimitGrant.cancel(user_id)
    flash("✅ تم إلغاء الحد المخصص، رجع المستخدم للحد الافتراضي.", "success")
    return redirect(url_for('admin.bot_limits_list'))
