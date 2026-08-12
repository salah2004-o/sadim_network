from flask import Blueprint, request, render_template, flash, redirect, url_for, session
from models.user import User
from models.verification_token import Email
from datetime import datetime, timedelta
import uuid
from utlis.email_utils import send_verification_email
from db.sadim_db import get_db_connection
from app.limiter import limiter

register_bp = Blueprint('register', __name__)

@register_bp.route('/register', methods=['GET'])
@limiter.limit("5 per minute")
def show_registration_form():
    return render_template('auth/register.html')

@register_bp.route('/register', methods=['POST'])
@limiter.limit("5 per minute")

def register_user():

    username = request.form.get('username')
    email = request.form.get('email')
    name = request.form.get('name')
    password = request.form.get('password')
    confirm = request.form.get('confirm') 

    if password != confirm:
        flash('كلمة المرور غير متطابقة', 'danger')
        return render_template('auth/register.html')
    # تحقق من username
    if User.get_by_username(username):
     flash('اسم المستخدم مستخدم بالفعل', 'danger')
     return render_template('auth/register.html')

# تحقق من email
    if User.get_by_email(email):
      flash('البريد الإلكتروني مستخدم بالفعل', 'danger')
      return render_template('auth/register.html')


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

        flash('تم إنشاء حسابك بنجاح! وصلَك رابط تفعيل على بريدك — يمكنك تصفّح الموقع الآن.', 'success')
        return redirect(url_for('loading_bp.landing_page'))
    except Exception as e:
     import traceback
     traceback.print_exc()
     flash('خطأ داخلي، راجع السيرفر', 'danger')
     return render_template('auth/register.html')

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