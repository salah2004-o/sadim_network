#settings.py
# هذا الملف يحتوي على إعدادات التطبيق، مثل إعدادات قاعدة البيانات، البريد الإلكتروني، وأي إعدادات أخرى يحتاجها التطبيق.
# يتم تحميل المتغيرات من ملف .env باستخدام مكتبة python-dotenv، مما يسهل إدارة الإعدادات بشكل آمن ومرن.
# evn file should be in the same directory as this settings.py file
import os
from dotenv import load_dotenv
import redis

# تحديد مسار ملف .env بدقة
dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path)

# ===== إعدادات Flask =====
SECRET_KEY = os.getenv("SECRET_KEY", "fallback_secret_key")
SESSION_TYPE = os.getenv("SESSION_TYPE", "redis")

REDIS_URL = os.getenv("REDIS_URL")
SESSION_REDIS = redis.from_url(REDIS_URL) if REDIS_URL else None

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "Lax"

# ===== إعدادات قاعدة البيانات =====
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT", 5432))

APP_URL = os.getenv("APP_URL")

# ===== إعدادات البريد =====
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.resend.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 587))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True") == "True"
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "False") == "True"
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_DEFAULT_SENDER = EMAIL_USER

# ===== إعدادات البوت =====
TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# ===== إعدادات Google OAuth =====
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
BOT_WORKER = os.getenv("BOT_WORKER", "true").lower() != "false"  # شغّل البوتات فقط من worker رقم 1
# لأدوات الفحص/الاختبار المحلية: تشغيل `BOT_WORKER=false python ...` يمنع أي استيراد للتطبيق
# من تشغيل بوتات تيليجرام حقيقية (يفادي تعارض 409 مع أي سيرفر حقيقي شغّال أصلاً بنفس التوكن).

# فاصل زمني (بالساعات) بين كل نشر تلقائي لرواية جديدة بقناة كل بوت
BOOK_ANNOUNCE_INTERVAL_HOURS = int(os.getenv("BOOK_ANNOUNCE_INTERVAL_HOURS", 24))

# Gemini keys are intentionally read only by the backend AI service.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
SADEEM_AI_DAILY_LIMIT = int(os.getenv("SADEEM_AI_DAILY_LIMIT", 20))