import os
import uuid
from app.routes.shared import UPLOAD_FOLDER
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, g, make_response
import pytz
from datetime import datetime, timedelta
from models.user import User
from models.verification_token import Email
from db.sadim_db import get_db_connection
from app.limiter import limiter
from app import google_oauth
from utlis.email_utils import send_verification_email
from werkzeug.utils import secure_filename
from werkzeug.utils import secure_filename
from PIL import Image
from app.models.analytics_model import log_event, end_session, SESSION_COOKIE_NAME

loading_bp = Blueprint('loading_bp', __name__)


def _log_auth_event(event_type, user_id=None, metadata=None):
    """تسجيل حدث مصادقة بدون أي احتمال لكسر تدفق الدخول/الخروج الفعلي لو فشل التسجيل نفسه."""
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
            _log_auth_event("auth.login.failed", metadata={"email": email, "reason": "missing_fields"})
            return render_template("auth/login.html", error="بيانات الدخول غير صحيحة")

        user = User.authenticate(email, password)

        if not user:
            _log_auth_event("auth.login.failed", metadata={"email": email, "reason": "invalid_credentials"})
            return render_template("auth/login.html", error="بيانات الدخول غير صحيحة")

        # ملاحظة: التحقق من البريد (is_verified) لا يحجب تسجيل الدخول — الحساب يُنشأ
        # مفعّلاً للاستخدام الأساسي فوراً (نفس نمط Google OAuth)، والتوثيق يبقى حالة
        # تُعرض للمستخدم (وقابلة لإكمالها لاحقاً عبر إعادة إرسال رابط التفعيل) بدل بوابة دخول.

        # بعد التحقق من المستخدم ونجاح تسجيل الدخول
        user.last_login = datetime.now()

        User.update_user(user)  # تأكد من أن update_user تقوم بتحديث last_login في قاعدة البيانات
        session.clear()
        session['user_id'] = user.id
        session['role'] = user.role
        session['username'] = user.username
        session['email'] = user.email
        session['last_login'] = user.last_login.strftime("%Y-%m-%d %H:%M:%S")

        _log_auth_event("auth.login.success", user_id=user.id, metadata={"email": user.email, "method": "password"})

        if user.role == 'admin':
            return redirect(url_for('admin.services_dashboard'))  # اسم الدالة في Blueprint dashboard
        else:
            return redirect(url_for('loading_bp.landing_page'))
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

        is_new_user = existing is None

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
        session['email'] = email

        if is_new_user:
            _log_auth_event("auth.register", user_id=user_id, metadata={"email": email, "method": "google"})
        else:
            _log_auth_event("auth.login.success", user_id=user_id, metadata={"email": email, "method": "google"})

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
    from app.models.post_model import Post
    random_posts = Post.get_random(limit=3)
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
        user=user,
        random_posts=random_posts,
    )


@loading_bp.route("/account")
def account():
    if 'user_id' not in session:
        return redirect(url_for('loading_bp.login'))
    user = User.get_by_id(session['user_id'])

    from app.models.bot_model import Bot
    from app.models.bot_limit_model import BotLimitGrant
    from app.models.post_model import Post
    from app.models.referral_model import Referral

    my_bots = Bot.get_by_user(session['user_id'])
    limit_status = BotLimitGrant.get_status_for_user(session['user_id'], current_bot_count=len(my_bots))
    my_articles = Post.get_by_user(session['user_id'])
    referral_count = Referral.get_referral_count(session['user_id'])
    referral_link = url_for('register.show_registration_form', ref=session['user_id'], _external=True)
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT content_type, COALESCE(book_id, article_id), added_at, COALESCE(b.title, p.title) FROM user_favorites f LEFT JOIN books b ON b.id=f.book_id LEFT JOIN posts p ON p.id=f.article_id WHERE f.user_id=%s ORDER BY added_at DESC LIMIT 10", (session['user_id'],))
        favorites = cur.fetchall()
        cur.execute("SELECT content_type, COALESCE(book_id, article_id), status, last_updated, COALESCE(b.title, p.title) FROM reading_history h LEFT JOIN books b ON b.id=h.book_id LEFT JOIN posts p ON p.id=h.article_id WHERE h.user_id=%s ORDER BY last_updated DESC LIMIT 10", (session['user_id'],))
        reading_history = cur.fetchall()
    finally:
        conn.close()

    return render_template(
        'account.html',
        user=user,
        limit_status=limit_status,
        my_bots=my_bots,
        my_articles=my_articles,
        referral_count=referral_count,
        referral_link=referral_link,
        favorites=favorites,
        reading_history=reading_history,
    )


@loading_bp.route('/resend_verification', methods=['POST'])
@limiter.limit("3 per minute")
def resend_verification():
    if 'user_id' not in session:
        return redirect(url_for('loading_bp.login'))

    user = User.get_by_id(session['user_id'])
    if not user:
        return redirect(url_for('loading_bp.login'))

    if user.is_verified:
        flash('بريدك موثّق بالفعل.', 'success')
        return redirect(url_for('loading_bp.account'))

    token = uuid.uuid4().hex
    expires_at = datetime.now() + timedelta(hours=1)
    Email.add_token(user.id, token, expires_at)

    try:
        send_verification_email(user.email, token)
        flash('تم إرسال رابط تفعيل جديد لبريدك الإلكتروني.', 'success')
    except Exception as e:
        print('Failed to resend verification email:', e)
        flash('تعذّر إرسال رابط التفعيل حالياً، حاول لاحقاً.', 'error')

    return redirect(url_for('loading_bp.account'))


@loading_bp.route('/logout')
def logout():
    user_id = session.get('user_id')
    if user_id:
        _log_auth_event("auth.logout", user_id=user_id)
        end_session(g.get('sd_session_id'))
    session.clear()
    # الجلسة التحليلية تنتهي فعلياً هنا — أي نشاط بعد الخروج (مسجّل أو مجهول) يبدأ جلسة جديدة، لا يُلحَق بجلسة أُنهيت للتو
    response = make_response(redirect(url_for('main.index')))
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@loading_bp.route("/account/settings", methods=['GET', 'POST'])
def account_settings():
    if 'user_id' not in session:
        return redirect(url_for('loading_bp.login'))
    user = User.get_by_id(session['user_id'])

    if request.method == 'POST':
        # معالجة تحديث الإعدادات
        name = request.form.get('name')
        email = request.form.get('email')
        bio = request.form.get('bio', '').strip()
        profile_image = request.files.get('profile_image')
        user.username = name
        user.email = email
        user.bio = bio or None
        if profile_image and profile_image.filename != "":
            filename = secure_filename(profile_image.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
    
            profile_image.save(filepath)
            user.profile_image = filename  # ✔ نخزن الاسم
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