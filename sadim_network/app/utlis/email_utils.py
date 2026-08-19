
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# إضافة المسار لجلب الإعدادات
from config import settings


def _send_email(to_email, subject, html_body):
    """منطق الإرسال المشترك (SMTP) — مستخرج من send_verification_email الأصلية بدون
    أي تغيير بسلوكها، حتى تقدر أي رسالة إيميل جديدة (زي تذكيرات حد البوتات) تعيد استخدامه."""
    if not all([settings.EMAIL_USER, settings.EMAIL_PASS, settings.APP_URL]):
        raise RuntimeError('Missing configuration: EMAIL_USER, EMAIL_PASS, or APP_URL')

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = settings.EMAIL_SENDER
    msg['To'] = to_email
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))

    try:
        print(f"🔌 محاولة الاتصال بـ {settings.EMAIL_HOST} عبر المنفذ {settings.EMAIL_PORT}...")
        if settings.EMAIL_USE_SSL:
            with smtplib.SMTP_SSL(settings.EMAIL_HOST, settings.EMAIL_PORT, timeout=15) as server:
                server.login(settings.EMAIL_USER, settings.EMAIL_PASS)
                server.send_message(msg)
        else:
            with smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT, timeout=15) as server:
                if settings.EMAIL_USE_TLS:
                    server.starttls()
                server.login(settings.EMAIL_USER, settings.EMAIL_PASS)
                server.send_message(msg)
        print(f"✅ تم إرسال البريد بنجاح إلى: {to_email}")
        return True
    except Exception as e:
        print(f"❌ فشل الإرسال: {e}")
        return False


def _sadeem_email_shell(title, body_html):
    """غلاف HTML موحّد لكل إيميلات سديم (نفس قالب بريد التحقق) — لتناسق كل الرسائل."""
    return f"""
    <html lang="ar" dir="rtl">
      <body style="margin:0; padding:0; background-color: #1a1a2e; font-family: sans-serif;">
        <table align="center" width="100%" style="max-width:600px; margin:40px auto; background:#ffffff; border-radius:16px; overflow:hidden; border: 1px solid #2b124c;">
          <tr>
            <td style="background: linear-gradient(135deg, #2b124c 0%, #522b5b 100%); padding:40px; text-align:center;">
              <h1 style="color:#dfb6b2; margin:0; font-size:28px;">SADEEM NETWORK</h1>
            </td>
          </tr>
          <tr>
            <td style="padding:40px; text-align: right; color:#2b124c;">
              <h2 style="color:#854f6c;">{title}</h2>
              {body_html.strip()}
            </td>
          </tr>
        </table>
      </body>
    </html>
    """


def send_verification_email(to_email, token):
    """إرسال بريد التحقق — بنفس القالب والمنطق الأصليين تماماً، بس عبر _send_email المشتركة الآن."""
    verify_link = f"{settings.APP_URL}/verify_email/{token}"
    body = f"""
              <p>مرحباً بك، خطوة واحدة تفصلك عن الانضمام لشبكة سديم التقنية. يرجى الضغط على الزر أدناه:</p>
              <div style="text-align:center; margin:30px 0;">
                <a href="{verify_link}" style="background:#854f6c; color:#ffffff; padding:15px 35px; text-decoration:none; border-radius:10px; display:inline-block; font-weight:bold;">تفعيل حسابي الآن</a>
              </div>
              <p style="font-size:12px; color:#666; border-top:1px solid #eee; padding-top:20px;">
                إذا واجهت مشكلة، انسخ الرابط: <br> {verify_link}
              </p>
    """
    html = _sadeem_email_shell("تفعيل الحساب ✨", body)
    return _send_email(to_email, 'تأكيد البريد الإلكتروني - شبكة سديم', html)


def send_bot_limit_reminder_email(to_email, username, days_left, expires_at, is_final=False):
    """تذكير بانتهاء صلاحية حد البوتات المخصص — يُرسل قبل 7 أيام (is_final=False)
    وعند الانتهاء الفعلي (is_final=True، يوضّح إن الحساب رجع للحد الافتراضي)."""
    expires_str = expires_at.strftime('%Y-%m-%d') if expires_at else ''
    if is_final:
        title = "انتهت صلاحية حد البوتات الإضافي"
        message = f"""
              <p>مرحباً {username}،</p>
              <p>انتهت صلاحية حد البوتات الإضافي الممنوح لحسابك بتاريخ <strong>{expires_str}</strong>،
                 ورجع حسابك تلقائياً للحد الافتراضي (بوت واحد).</p>
              <p>بوتاتك الحالية <strong>لن تُحذف</strong> — فقط ما تقدر تنشئ بوتات جديدة تتجاوز الحد الافتراضي.</p>
        """
    else:
        title = "صلاحية حد البوتات ستنتهي قريباً"
        message = f"""
              <p>مرحباً {username}،</p>
              <p>صلاحية حد البوتات الإضافي الممنوح لحسابك ستنتهي بعد <strong>{days_left} أيام</strong>،
                 بتاريخ <strong>{expires_str}</strong>.</p>
              <p>بعد الانتهاء، يرجع حسابك تلقائياً للحد الافتراضي (بوت واحد) — بدون حذف أي بوت موجود حالياً.</p>
        """
    body = message + """
              <p style="margin-top:20px;">لتجديد أو زيادة الحد، يرجى التواصل مع إدارة شبكة سديم.</p>
    """
    html = _sadeem_email_shell(title, body)
    subject = "انتهت صلاحية حد البوتات - شبكة سديم" if is_final else "تذكير: صلاحية حد البوتات تنتهي قريباً - شبكة سديم"
    return _send_email(to_email, subject, html)


# لم اكتبه بنفسي بل كتبه ai 