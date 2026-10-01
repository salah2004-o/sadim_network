from flask import Blueprint, request, render_template, flash, redirect, url_for, session, g
from models.user import User
from models.verification_token import Email
from datetime import datetime, timedelta
import uuid
from utlis.email_utils import send_verification_email
from db.sadim_db import get_db_connection
from app.limiter import limiter
from app.models.analytics_model import log_event, generate_session_id, touch_session, SESSION_COOKIE_NAME, audit_log
from app.models.bot_classifier import classify_visitor
from app.models.referral_model import Referral

register_bp = Blueprint('register', __name__)

# مسارات لا تُحتسب كنشاط تحليلي إطلاقاً — ملفات ثابتة وطلبات المتصفح الآلية
_STATIC_EXACT_PATHS = {"/favicon.ico", "/robots.txt", "/apple-touch-icon.png", "/apple-touch-icon-precomposed.png"}
_STATIC_EXTENSIONS = (".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp", ".woff", ".woff2", ".ttf")
# مسارات إدارية — تُبقي الجلسة حيّة (last_seen) لكن لا تُحتسب كـ"مشاهدة صفحة" بمقاييس تفاعل الزوار
_ADMIN_PATH_PREFIXES = ("/dashboard", "/profile")
# طلبات خلفية من JS (أحداث الواجهة، حفظ تقدم القراءة) — تُبقي الجلسة حيّة لكنها ليست مشاهدة صفحة
_BACKGROUND_PATH_PREFIXES = ("/api/events", "/api/personal/progress")


def _is_excluded_path(path):
    if path.startswith('/static/'):
        return True
    if path in _STATIC_EXACT_PATHS:
        return True
    if path.endswith(_STATIC_EXTENSIONS):
        return True
    return False


def _log_auth_event(event_type, user_id=None, metadata=None):
    """تسجيل حدث مصادقة بدون أي احتمال لكسر تدفق التسجيل الفعلي لو فشل التسجيل نفسه."""
    try:
        log_event(
            event_type,
            user_id=user_id,
            session_id=g.get('sd_session_id'),
            ip=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
            path=request.path,
            visitor_type=g.get('sd_visitor_type', 'unknown'),
            metadata=metadata,
        )
    except Exception as e:
        print(f"Failed to log analytics event '{event_type}':", e)

@register_bp.route('/register', methods=['GET'])
@limiter.limit("5 per minute")
def show_registration_form():
    # ref يمرَّر كحقل مخفي بالنموذج حتى يصل لـPOST /register — الرابط نفسه user_id المُحيل، بدون توليد كود جديد
    ref = request.args.get('ref', '')
    return render_template('auth/register.html', ref=ref)

@register_bp.route('/register', methods=['POST'])
@limiter.limit("5 per minute")

def register_user():

    username = request.form.get('username')
    email = request.form.get('email')
    name = request.form.get('name')
    password = request.form.get('password')
    confirm = request.form.get('confirm')
    ref = request.form.get('ref', '')  # نحافظ عليه بكل إعادة عرض للنموذج حتى لا تضيع الدعوة لو صار خطأ إدخال

    if password != confirm:
        flash('كلمة المرور غير متطابقة', 'danger')
        return render_template('auth/register.html', ref=ref)
    # تحقق من username
    if User.get_by_username(username):
     flash('اسم المستخدم مستخدم بالفعل', 'danger')
     return render_template('auth/register.html', ref=ref)

# تحقق من email
    if User.get_by_email(email):
      flash('البريد الإلكتروني مستخدم بالفعل', 'danger')
      return render_template('auth/register.html', ref=ref)


    # إنشاء كائن مستخدم جديد (نمرر كلمة المرور الخام؛ add_user سيقوم بالتشفير)
    new_user = User(username=username, email=email, name=name, password=password)

    try:
        user_id = new_user.add_to_db()  # دالة add_user من كلاس User تتوقع raw_password
        print('New user ID:', user_id)
        # إنشاء رمز تحقق وحفظه
        token = uuid.uuid4().hex
        expires_at = datetime.now() + timedelta(hours=1)
        Email.add_token(user_id, token, expires_at)

        # إرسال بريد التحقق
        try:
            send_verification_email(email, token)
            print('Verification email sent successfully')
        except Exception as e:
            # لا نوقف التسجيل لو فشل الإرسال لكن نعلم المطور
            print('Failed to send verification email:', e)

        # تسجيل دخول تلقائي فور إنشاء الحساب (بنفس نمط مسار Google OAuth تماماً) —
        # التحقق من البريد يبقى مطلوباً لاحقاً لكنه لا يمنع الوصول الأساسي للموقع
        session.clear()
        session['user_id'] = user_id
        session['role'] = 'user'
        session['username'] = username
        session['email'] = email

        _log_auth_event("auth.register", user_id=user_id, metadata={"email": email, "method": "password"})

        # دعوة صديق: الرابط نفسه user_id المُحيل (?ref=42) — تحقق رقمي بسيط، فشل صامت آمن لأي قيمة غير صالحة
        ref_raw = request.form.get('ref', '').strip()
        if ref_raw.isdigit():
            rewarded = Referral.record_and_reward(int(ref_raw), user_id)
            if rewarded:
                _log_auth_event("referral.success", user_id=user_id, metadata={"referrer_user_id": int(ref_raw)})

        flash('تم إنشاء حسابك بنجاح! وصلَك رابط تفعيل على بريدك — يمكنك تصفّح الموقع الآن.', 'success')
        return redirect(url_for('loading_bp.landing_page'))
    except Exception as e:
     import traceback
     traceback.print_exc()
     flash('خطأ داخلي، راجع السيرفر', 'danger')
     return render_template('auth/register.html', ref=ref)

    # بعد حفظ المستخدم في جدول users
@register_bp.before_app_request
def log_visitor():
    # تجاهل الملفات الثابتة
    if request.path.startswith('/static/'):
        return

    ip = request.remote_addr
    user_agent = request.headers.get("User-Agent")
    path = request.path

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO visitor_logs (ip, user_agent, path) VALUES (%s, %s, %s)",
            (ip, user_agent, path)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print("Failed to log visitor:", e)


@register_bp.before_app_request
def track_session():
    """جلسة تحليلية حقيقية (analytics_sessions) — منفصلة تماماً عن جلسة المصادقة (Flask session).
    كوكي خاص (sd_sid) بدل الاعتماد على session['user_id'] حتى تُتتبَّع الجلسات المجهولة أيضاً،
    وتستمر نفس الجلسة التحليلية حتى بعد ما يسجّل الزائر دخوله (ربط لا استبدال)."""
    if _is_excluded_path(request.path):
        return

    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    is_new = not session_id
    if is_new:
        session_id = generate_session_id()

    g.sd_session_id = session_id
    g.sd_session_is_new = is_new
    g.sd_visitor_type = classify_visitor(
        request.path, request.headers.get("User-Agent"), request.remote_addr, request.headers
    )

    is_admin_path = request.path.startswith(_ADMIN_PATH_PREFIXES)
    is_admin_actor = session.get('role') == 'admin'

    # نشاط الإدارة الفعلي (أدمن يتصفّح لوحته) يُسجَّل بسجل منفصل تماماً (audit_logs)،
    # ولا يُنشئ/يُحدّث أي جلسة بـanalytics_sessions — حتى لا يختلط بإحصائيات المستخدمين/الزوار العامة إطلاقاً
    if is_admin_path and is_admin_actor:
        try:
            audit_log(
                actor_user_id=session.get('user_id'),
                action="admin_page_view",
                target_type="path",
                ip=request.remote_addr,
                metadata={"path": request.path},
            )
        except Exception as e:
            print("Failed to write audit log:", e)
        return

    try:
        touch_session(
            session_id,
            user_id=session.get('user_id'),
            ip=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
            referrer=request.referrer if is_new else None,
            landing_page=request.path if is_new else None,
            count_pageview=not is_admin_path and not request.path.startswith(_BACKGROUND_PATH_PREFIXES),
            visitor_type=g.sd_visitor_type,
            utm_source=request.args.get('utm_source') if is_new else None,
            utm_medium=request.args.get('utm_medium') if is_new else None,
            utm_campaign=request.args.get('utm_campaign') if is_new else None,
            utm_content=request.args.get('utm_content') if is_new else None,
        )
    except Exception as e:
        print("Failed to track session:", e)


@register_bp.after_app_request
def set_session_cookie(response):
    session_id = g.get('sd_session_id')
    if session_id and g.get('sd_session_is_new'):
        response.set_cookie(
            SESSION_COOKIE_NAME, session_id,
            max_age=60 * 60 * 24 * 365,  # سنة — الجلسة التحليلية نفسها "تنتهي" منطقياً بعد فترة ركود، لا بانتهاء الكوكي
            httponly=True, samesite='Lax'
        )
    return response


@register_bp.before_app_request
def log_user_activity():
    # نتتبع فقط الجلسات المسجّلة دخول
    user_id = session.get('user_id')
    if not user_id:
        return
    if request.path.startswith('/static/'):
        return

    ip = request.remote_addr
    user_agent = request.headers.get("User-Agent")
    email = session.get('email')
    username = session.get('username')

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE user_logs SET created_at = NOW(), email = %s, username = %s, ip = %s, user_agent = %s WHERE user_id = %s",
            (email, username, ip, user_agent, user_id)
        )
        if cur.rowcount == 0:
            cur.execute(
                "INSERT INTO user_logs (user_id, email, username, ip, user_agent) VALUES (%s, %s, %s, %s, %s)",
                (user_id, email, username, ip, user_agent)
            )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print("Failed to log user activity:", e)