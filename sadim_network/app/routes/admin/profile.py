from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.db.sadim_db import get_db_connection
from app.utlis.permissions import admin_required
from app.utlis.login_required import login_required

# تم توليد هذا الملف بواسطة AI، قد يحتوي على أخطاء أو يحتاج إلى تحسينات. يرجى مراجعته بعناية قبل الاستخدام.
# رغم انني استطيع بناء هذا الملف من الصفر، الا انني استخدمت بعض الكود من ملفات اخرى لتسريع العملية، لذا قد تجد بعض التشابهات في الكود مع ملفات اخرى في المشروع.
# هو شيء بسيط لهذا استخدمت AI لإنشاء هذا الملف، لكني قمت بتعديله وتحسينه ليتناسب مع احتياجات المشروع. اذا وجدت اي خطأ او لديك اي اقتراحات لتحسين الكود، لا تتردد في مشاركتها معي. شكرا لتفهمك!

profile_bp = Blueprint('profile_bp', __name__, url_prefix='/profile')


# ── Helpers ───────────────────────────────────────────────────────────────────
# أضف هذه الدالة في قسم الـ Helpers في بداية الملف
def is_bot(user_agent):
    """التحقق مما إذا كان الزائر بوت أو زاحف ويب لضمان دقة الإحصائيات"""
    bots = ['bot', 'spider', 'crawl', 'facebookexternalhit', 'snapchat', 'whatsapp', 'preview']
    user_agent = user_agent.lower()
    return any(bot in user_agent for bot in bots)

def get_profile():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM profile;")
    data = {row[0]: row[1] for row in cur.fetchall()}
    cur.close()
    conn.close()
    return data

def get_stats():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, label, value FROM profile_stats ORDER BY id;")
    rows = [{'id': r[0], 'label': r[1], 'value': r[2]} for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows

def get_skills():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, level FROM profile_skills ORDER BY id;")
    rows = [{'id': r[0], 'name': r[1], 'level': r[2]} for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows

def get_projects():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, description, url, tags FROM profile_projects ORDER BY id;")
    rows = [{'id': r[0], 'name': r[1], 'desc': r[2], 'url': r[3], 'tags': r[4]} for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows

def get_certs():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, title, issuer, date, description FROM profile_certificates ORDER BY id;")
    rows = [{'id': r[0], 'title': r[1], 'issuer': r[2], 'date': r[3], 'desc': r[4]} for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


# ── Dashboard ────────────────────────────────────────────────────────────────

@profile_bp.route('/profile')
@login_required
@admin_required
def profile_dashboard():
    return render_template('dashboard/profile_dashboard.html',
        info=get_profile(), stats=get_stats(),
        skills=get_skills(), projects=get_projects(), certs=get_certs()
    )


# ── General Info ─────────────────────────────────────────────────────────────

@profile_bp.route('/profile/info', methods=['POST'])
@login_required
@admin_required
def profile_update_info():
    conn = get_db_connection()
    cur = conn.cursor()
    for field in ['name', 'title', 'tagline', 'bio', 'github', 'telegram', 'website', 'available']:
        val = request.form.get(field, '').strip()
        cur.execute("""
            INSERT INTO profile (key, value)
            VALUES (%s, %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();
        """, (field, val))
    conn.commit()
    cur.close()
    conn.close()
    flash('تم حفظ البيانات العامة', 'success')
    return redirect(url_for('profile_bp.profile_dashboard'))


# ── Stats ─────────────────────────────────────────────────────────────────────

@profile_bp.route('/profile/stats/add', methods=['POST'])
@login_required
@admin_required
def profile_stat_add():
    label = request.form.get('label', '').strip()
    value = request.form.get('value', '').strip()
    if label and value:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO profile_stats (label, value) VALUES (%s, %s);", (label, value))
        conn.commit()
        cur.close()
        conn.close()
        flash('تمت إضافة الإحصائية', 'success')
    return redirect(url_for('profile_bp.profile_dashboard') + '#stats')


@profile_bp.route('/profile/stats/update/<int:stat_id>', methods=['POST'])
@login_required
@admin_required
def profile_stat_update(stat_id):
    label = request.form.get('label', '').strip()
    value = request.form.get('value', '').strip()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE profile_stats SET label=%s, value=%s WHERE id=%s;", (label, value, stat_id))
    conn.commit()
    cur.close()
    conn.close()
    flash('تم تحديث الإحصائية', 'success')
    return redirect(url_for('profile_bp.profile_dashboard') + '#stats')


@profile_bp.route('/profile/stats/delete/<int:stat_id>', methods=['POST'])
@login_required
@admin_required
def profile_stat_delete(stat_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM profile_stats WHERE id=%s;", (stat_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash('تم حذف الإحصائية', 'success')
    return redirect(url_for('profile_bp.profile_dashboard') + '#stats')


# ── Skills ────────────────────────────────────────────────────────────────────

@profile_bp.route('/profile/skills/add', methods=['POST'])
@login_required
@admin_required
def profile_skill_add():
    name = request.form.get('name', '').strip()
    level = int(request.form.get('level', 50))
    if name:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO profile_skills (name, level) VALUES (%s, %s);", (name, level))
        conn.commit()
        cur.close()
        conn.close()
        flash('تمت إضافة المهارة', 'success')
    return redirect(url_for('profile_bp.profile_dashboard') + '#skills')


@profile_bp.route('/profile/skills/update/<int:skill_id>', methods=['POST'])
@login_required
@admin_required
def profile_skill_update(skill_id):
    name = request.form.get('name', '').strip()
    level = int(request.form.get('level', 50))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE profile_skills SET name=%s, level=%s WHERE id=%s;", (name, level, skill_id))
    conn.commit()
    cur.close()
    conn.close()
    flash('تم تحديث المهارة', 'success')
    return redirect(url_for('profile_bp.profile_dashboard') + '#skills')


@profile_bp.route('/profile/skills/delete/<int:skill_id>', methods=['POST'])
@login_required
@admin_required
def profile_skill_delete(skill_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM profile_skills WHERE id=%s;", (skill_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash('تم حذف المهارة', 'success')
    return redirect(url_for('profile_bp.profile_dashboard') + '#skills')


# ── Projects ──────────────────────────────────────────────────────────────────

@profile_bp.route('/profile/projects/add', methods=['POST'])
@login_required
@admin_required
def profile_project_add():
    name = request.form.get('name', '').strip()
    desc = request.form.get('desc', '').strip()
    url  = request.form.get('url', '').strip()
    tags = request.form.get('tags', '').strip()
    if name:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO profile_projects (name, description, url, tags) VALUES (%s, %s, %s, %s);",
            (name, desc, url, tags)
        )
        conn.commit()
        cur.close()
        conn.close()
        flash('تمت إضافة المشروع', 'success')
    return redirect(url_for('profile_bp.profile_dashboard') + '#projects')


@profile_bp.route('/profile/projects/update/<int:proj_id>', methods=['POST'])
@login_required
@admin_required
def profile_project_update(proj_id):
    name = request.form.get('name', '').strip()
    desc = request.form.get('desc', '').strip()
    url  = request.form.get('url', '').strip()
    tags = request.form.get('tags', '').strip()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE profile_projects SET name=%s, description=%s, url=%s, tags=%s WHERE id=%s;",
        (name, desc, url, tags, proj_id)
    )
    conn.commit()
    cur.close()
    conn.close()
    flash('تم تحديث المشروع', 'success')
    return redirect(url_for('profile_bp.profile_dashboard') + '#projects')


@profile_bp.route('/profile/projects/delete/<int:proj_id>', methods=['POST'])
@login_required
@admin_required
def profile_project_delete(proj_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM profile_projects WHERE id=%s;", (proj_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash('تم حذف المشروع', 'success')
    return redirect(url_for('profile_bp.profile_dashboard') + '#projects')


# ── Certificates ──────────────────────────────────────────────────────────────

@profile_bp.route('/profile/certs/add', methods=['POST'])
@login_required
@admin_required
def profile_cert_add():
    title  = request.form.get('title', '').strip()
    issuer = request.form.get('issuer', '').strip()
    date   = request.form.get('date', '').strip()
    desc   = request.form.get('desc', '').strip()
    if title:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO profile_certificates (title, issuer, date, description) VALUES (%s, %s, %s, %s);",
            (title, issuer, date, desc)
        )
        conn.commit()
        cur.close()
        conn.close()
        flash('تمت إضافة الشهادة', 'success')
    return redirect(url_for('profile_bp.profile_dashboard') + '#certs')


@profile_bp.route('/profile/certs/update/<int:cert_id>', methods=['POST'])
@login_required
@admin_required
def profile_cert_update(cert_id):
    title  = request.form.get('title', '').strip()
    issuer = request.form.get('issuer', '').strip()
    date   = request.form.get('date', '').strip()
    desc   = request.form.get('desc', '').strip()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE profile_certificates SET title=%s, issuer=%s, date=%s, description=%s WHERE id=%s;",
        (title, issuer, date, desc, cert_id)
    )
    conn.commit()
    cur.close()
    conn.close()
    flash('تم تحديث الشهادة', 'success')
    return redirect(url_for('profile_bp.profile_dashboard') + '#certs')


@profile_bp.route('/profile/certs/delete/<int:cert_id>', methods=['POST'])
@login_required
@admin_required
def profile_cert_delete(cert_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM profile_certificates WHERE id=%s;", (cert_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash('تم حذف الشهادة', 'success')
    return redirect(url_for('profile_bp.profile_dashboard') + '#certs')


# ── Public Page ───────────────────────────────────────────────────────────────

# ── Public Page ───────────────────────────────────────────────────────────────

@profile_bp.route('/profile/view')
def profile_public():
    user_agent = request.headers.get('User-Agent', '')

    # 1. تحديث العداد فقط إذا لم يكن الزائر بوت
    if not is_bot(user_agent):
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            # 2. تحديث عداد المشاهدات في جدول profile_stats
            # استخدمنا COALESCE للتعامل مع الحالة التي قد لا يكون فيها الحقل موجوداً أو فارغاً
            cur.execute("""
                UPDATE profile_stats 
                SET value = (COALESCE(NULLIF(value, ''), '0')::INTEGER + 1)::TEXT 
                WHERE label = 'views';
            """)
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            # نسجل الخطأ في السيرفر لكن لا نعطل عرض الصفحة للمستخدم
            print(f"Error updating views: {e}")

    # 3. عرض الصفحة مع البيانات المحدثة
    return render_template('profile/profiles.html',
        info=get_profile(), stats=get_stats(),
        skills=get_skills(), projects=get_projects(), certs=get_certs()
    )