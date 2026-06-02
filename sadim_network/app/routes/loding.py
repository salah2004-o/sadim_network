import os
from app.routes.shared import UPLOAD_FOLDER
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
import pytz
from datetime import datetime
from models.user import User
from db.sadim_db import get_db_connection
from app.limiter import limiter
from app import google_oauth
from werkzeug.utils import secure_filename
from werkzeug.utils import secure_filename
from PIL import Image

loading_bp = Blueprint('loading_bp', __name__)

@loading_bp.route('/login')
@limiter.limit("5 per minute")
def login_page():
    return render_template(
        'auth/login.html',
        current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

@loading_bp.route('/login', methods=['POST'])
@limiter.limit("5 per minute")  
def login():
    try:
        email = request.form.get('email')
        password = request.form.get('password')
        if not email or not password:
            flash("erros")
            return render_template("auth/login.html", error="بيانات الدخول غير صحيحة")
        
        user = User.authenticate(email, password)

        if not user:
            return render_template("auth/login.html", error="بيانات الدخول غير صحيحة")
        
        if not user.is_verified and user.role !='admin':

            return render_template("auth/login.html", error="يرجي التحقق من بريدك الإلكتروني قبل تسجيل الدخول.")
        
        # بعد التحقق من المستخدم ونجاح تسجيل الدخول
        user.last_login = datetime.now()

        User.update_user(user)  # تأكد من أن update_user تقوم بتحديث last_login في قاعدة البيانات
        session.clear()
        session['user_id'] = user.id
        session['role'] = user.role
        session['username'] = user.username
        session['last_login'] = user.last_login.strftime("%Y-%m-%d %H:%M:%S")
        
        if user.role == 'admin':
            return redirect(url_for('admin.services_dashboard'))  # اسم الدالة في Blueprint dashboard
        else:
            return redirect(url_for('admin.show_services'))  # اسم الدالة في Blueprint show_services       
    except Exception as e:
        return render_template("auth/login.html", error="حدث خطأ أثناء تسجيل الدخول. يرجى المحاولة مرة أخرى.")
    
@loading_bp.route('/auth/google')
def google_login():
    redirect_uri = url_for('loading_bp.google_auth_callback', _external=True)
    return google_oauth.authorize_redirect(redirect_uri)


@loading_bp.route('/auth/google/callback')
def google_auth_callback():
    try:
        token = google_oauth.authorize_access_token()
        user_info = token.get('userinfo')
        email = user_info.get('email')
        google_id = user_info.get('sub')
        name = user_info.get('name', "")
        picture = user_info.get('picture', '')

        conn = get_db_connection()
        cur = conn.cursor()
        # هل المستخدم موجود؟
        cur.execute("SELECT id, role, username FROM users WHERE google_id = %s OR email = %s", (google_id, email))
        existing = cur.fetchone()

        if existing:
            user_id, role, username = existing
            # تحديث google_id لو سجل قبل بإيميل
            cur.execute("UPDATE users SET google_id = %s WHERE id = %s", (google_id, user_id))
        else:
            # مستخدم جديد
            username = email.split('@')[0]
            cur.execute("""
                INSERT INTO users (username, name, email, google_id, is_verified, profile_image, password_hash)
                VALUES (%s, %s, %s, %s, TRUE, %s, NULL)
                RETURNING id, role
            """, (username, name, email, google_id, picture))
            user_id, role = cur.fetchone()

        conn.commit()
        cur.close()
        conn.close()
        session.clear()
        session['user_id'] = user_id
        session['role'] = role
        session['username'] = username

        if role == 'admin':
            return redirect(url_for('admin.services_dashboard'))
        else:
            return redirect(url_for('admin.show_services'))

    except Exception as e:
        print(f"❌ خطأ في Google OAuth: {e}")
        return render_template('auth/login.html', error="حدث خطأ أثناء تسجيل الدخول بـ Google")

@loading_bp.route('/landing')
def landing_page():
    if 'user_id' not in session:
        return redirect(url_for('loading_bp.login'))
    # اسم المستخدم من session
    username = session.get('username', 'ضيف')
    user = User.get_by_id(session['user_id'])
    # الوقت الحالي حسب منطقتك
    tz = pytz.timezone("Africa/Tripoli")
    now = datetime.now(tz)
    current_time = now.strftime("%Y-%m-%d")

    # تحديد التحية حسب الوقت
    hour = now.hour
    if 5 <= hour < 12:
        greeting = "صباح الخير"
    elif 12 <= hour < 17:
        greeting = "مساء النور"
    else:
        greeting = "مساء الخير"

    # إرسال المعلومات للصفحة
    return render_template(
        'landing.html',
        username=username,
        greeting=greeting,
        current_time=current_time,
        user=user
    )


@loading_bp.route("/account")
def account():
    if 'user_id' not in session:
        return redirect(url_for('loading_bp.login'))
    user = User.get_by_id(session['user_id'])
    return render_template('account.html', user=user)


@loading_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('main.index'))


@loading_bp.route("/account/settings", methods=['GET', 'POST'])
def account_settings():
    if 'user_id' not in session:
        return redirect(url_for('loading_bp.login'))
    user = User.get_by_id(session['user_id'])

    if request.method == 'POST':
        # معالجة تحديث الإعدادات
        name = request.form.get('name')
        email = request.form.get('email')
        profile_image = request.files.get('profile_image')
        user.username = name
        user.email = email
        if profile_image and profile_image.filename != "":
            filename = secure_filename(profile_image.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
    
            profile_image.save(filepath)
            user.profile_image = filename  # ✔ نخزن الاسم  
        user.update_user()      
        if delete := request.form.get('delete_account'):
            # معالجة حذف الحساب
            User.delete(user.id)
            session.clear()
            return redirect(url_for('main.index'))
        # استدعاء update وتخزين النتيجة
        result = user.update_user()
        # التحقق من أي خطأ
        if "error" in result:
            if result["error"] == "email_exists":
                return render_template(
                    "account_settings.html",
                    user=user,
                    error="البريد الإلكتروني مستخدم بالفعل"
                )
            else:
                return render_template(
                    "account_settings.html",
                    user=user,
                    error="حدث خطأ أثناء تحديث الحساب"
                )
        # إذا كل شيء تمام
        return redirect(url_for('loading_bp.account'))

    # GET request
    return render_template('account_settings.html', user=user)

@loading_bp.route('/verify_email/<token>')
def verify_email(token):
    """
    التحقق من البريد الإلكتروني باستخدام الرمز (Token)
    """
    try:
        # البحث عن الرمز في قاعدة البيانات
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, user_id, expires_at, is_used
            FROM email_verifications
            WHERE token = %s
        """, (token,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        
        if not row:
            # عرض صفحة فشل التحقق
            return render_template('verify_failure.html')
        
        token_id, user_id, expires_at, is_used = row
        
        # التحقق من انتهاء الصلاحية
        if datetime.now() > expires_at:
            return render_template('verify_failure.html')
        
        # التحقق من عدم استخدام الرمز مسبقاً
        if is_used:
            return render_template('verify_failure.html')
        
        # تحديث حالة المستخدم إلى verified
        User.verify_email(user_id)  # أو verify_user_email(user_id)
        
        # تحديث حالة الرمز إلى is_used
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE email_verifications
            SET is_used = TRUE
            WHERE id = %s
        """, (token_id,))
        conn.commit()
        cur.close()
        conn.close()
        # عرض صفحة نجاح التحقق
        return render_template('verify_success.html', login=url_for('loading_bp.login'))
        
    except Exception as e:
        print(f"❌ خطأ في التحقق من البريد: {e}")
        return render_template('verify_failure.html')