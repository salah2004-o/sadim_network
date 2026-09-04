# مخطط مشروع شبكة سديم للخدمات الرقمية 🏗️

```
sadim_network/
│
├── 📄 run.py                    # نقطة تشغيل التطبيق الرئيسية
│
└── 📁 app/                      # مجلد التطبيق الأساسي (Flask)
    │
    ├── 📄 __init__.py           # تهيئة تطبيق Flask
    ├── 📄 limiter.py            # إعدادات التحديد/الحماية (Rate Limiting)
    │
    ├── 📁 config/               # ملفات الإعدادات والتكوين
    │   ├── 📄 .env              # متغيرات البيئة
    │   └── 📄 settings.py       # إعدادات التطبيق
    │
    ├── 📁 db/                   # طبقة قاعدة البيانات
    │   └── 📄 sadim_db.py       # إعدادات وعمليات قاعدة البيانات
    │
    ├── 📁 models/               # نماذج البيانات (ORM Models)
    │   ├── 📄 product.py        # نموذج المنتج
    │   ├── 📄 user.py           # نموذج المستخدم
    │   └── 📄 verification_token.py  # نموذج رموز التحقق
    │
    ├── 📁 routes/               # المسارات والتوجيهات (Routes)
    │   ├── 📄 admin.py          # مسارات إدارة النظام
    │   ├── 📄 index.py          # المسارات الرئيسية
    │   ├── 📄 register.py       # مسارات التسجيل
    │   ├── 📄 loding.py         # مسارات التحميل
    │   ├── 📄 errors.py         # معالجة الأخطاء
    │   │
    │   ├── 📁 apis/             # واجهات برمجية (API)
    │   │   └── 📄 chatbot_api.py
    │   │
    │   ├── 📁 LIBRARY_SADIM/    # نطاق مكتبة سديم
    │   │   ├── 📄 Agatha_Christie.py
    │   │   └── 📁 static/
    │   │
    │   └── 📁 Repository/       # Repository Pattern (Business Logic)
    │       ├── 📄 auth_service.py
    │       └── 📄 user_update.py
    │
    ├── 📁 static/               # الملفات الثابتة
    │   ├── 📁 css/              # ملفات الأنماط
    │   │   ├── 📁 dashboard/
    │   │   └── 📁 services/
    │   ├── 📁 fonts/            # الخطوط
    │   ├── 📁 images/           # الصور
    │   └── 📁 uploads/          # ملفات المستخدمين
    │
    ├── 📁 templates/            # قوالب HTML (Jinja2)
    │   ├── 📄 base.html
    │   ├── 📄 index.html
    │   ├── 📄 landing.html
    │   ├── 📄 account.html
    │   ├── 📄 account_settings.html
    │   ├── 📄 verify_success.html
    │   ├── 📄 verify_failure.html
    │   ├── 📄 404.html
    │   ├── 📁 auth/
    │   ├── 📁 dashboard/
    │   └── 📁 Agatha Christie/
    │
    └── 📁 utils/                # الأدوات المساعدة (Utilities)
        ├── 📄 apply_sadim_brand.py
        ├── 📄 email_utils.py
        ├── 📄 login_required.py
        └── 📄 permissions.py
```

---

## 📋 وصف الهيكل (محدّث):

### المجلدات الرئيسية:

| المجلد             | الغرض                           |
| ------------------ | ------------------------------- |
| **app/**           | منطق التطبيق الكامل (Flask App) |
| **app/config/**    | إعدادات البيئة والتكوين         |
| **app/db/**        | الاتصال بقاعدة البيانات         |
| **app/models/**    | نماذج ORM                       |
| **app/routes/**    | Routes + APIs + Domains         |
| **app/static/**    | CSS / Images / Uploads / Fonts  |
| **app/templates/** | واجهة المستخدم (Jinja2)         |
| **app/utils/**     | Middlewares وHelpers            |

---

## 🔄 العلاقات بين المكونات (كما في المشروع الفعلي):

```
run.py
  ↓
app/__init__.py
  ├─ config/settings.py
  ├─ limiter.py
  ├─ db/sadim_db.py
  ├─ models/*
  ├─ routes/
  │    ├─ admin.py
  │    ├─ index.py
  │    ├─ register.py
  │    ├─ loding.py
  │    ├─ errors.py
  │    ├─ apis/chatbot_api.py
  │    └─ Repository/*
  ├─ templates/*
  ├─ static/*
  └─ utils/*
```

---

## 🎯 نوع المشروع:

**Flask Backend System (Production-Oriented)** يدعم:

* نظام مستخدمين + تحقق
* أدوار وصلاحيات
* لوحة إدارة
* API Layer
* Domain مستقل (Library Sadim)
* واجهة عربية
* قابل للتوسع إلى SaaS

## Sadeem AI

يعمل Sadeem AI من خلال `app/models/ai_service.py` ويمرر كل طلب عبر Backend سديم. لا يصل Gemini إلى قاعدة البيانات مباشرة؛ الأدوات المقيدة فقط هي التي تنفذ استعلامات المكتبة والمقالات والخدمات وسياق المستخدم غير الحساس.

قبل التشغيل على الخادم، أضف في `app/config/.env` (ولا تضع هذه القيم في JavaScript أو Git):

```env
GEMINI_API_KEY_1=your-server-secret
GEMINI_API_KEY_2=your-second-server-secret
GEMINI_MODEL=gemini-3.6-flash
SADEEM_AI_DAILY_LIMIT=20
```

شغّل `python app/db/sadim_db.py` مرة واحدة لإنشاء جداول `ai_conversations` و`ai_messages` و`ai_usage` و`ai_user_knowledge`. صفحة المستخدم هي `/ai/`، وسجل الإدارة المحمي هو `/dashboard/ai-conversations`.

المحادثات محصورة بالمستخدم صاحبها، وسياق Gemini محدود بآخر 16 رسالة وبحد أقصى 4000 حرف للرسالة. يتم تدوير مفاتيح Gemini عند الفشل، وتسجيل الاستخدام، وتسجيل وصول الإدارة في `audit_logs`.

---

  _____                   _                  _____
 |_   _| __  _ __  _   _ | |_  ___  _ __    |_   _|  ___  ___  ___
   | || '__|| '__|| | | || __|/ _ \| '__|     | |   / _ \/ __|/ _ \
   | || |   | |   | |_| || |_|  __/| |        | |  |  __/\__ \  __/
   |_||_|   |_|    \__,_| \__|\___||_|        |_|   \___||___/\___|
               TextureDev -- Crafting digital textures
