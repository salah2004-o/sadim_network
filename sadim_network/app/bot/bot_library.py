import os
import json
import time
import pytz
import telebot
from telebot import types
from datetime import datetime, timezone
from models.library_mdl import Library
from config.settings import TOKEN, ADMIN_ID, DAILY_NOVEL_HOUR, DAILY_NOVEL_MINUTE
from app.db.sadim_db import get_db_connection
from app.bot.services import users_db
from app.bot.services import daily_novel as daily_novel_svc

# ══════════════════════════════════════════
#                الإعدادات والمتغيرات
# ════════════════════════════════════════

bot = telebot.TeleBot(TOKEN, threaded=True, num_threads=15)

# التخزين المؤقت وحالات المستخدمين
verified_cache = {}
user_states = {}
forwarded_msgs = {}

# ══════════════════════════════════════════
#                دوال قاعدة البيانات
# ══════════════════════════════════════════

def execute_query(query, params=(), fetch=False, fetchall=False, commit=False):
    conn = get_db_connection()
    cur = conn.cursor()
    result = None
    try:
        cur.execute(query, params)
        if commit:
            conn.commit()
        if fetch:
            result = cur.fetchone()
        if fetchall:
            result = cur.fetchall()
    finally:
        cur.close()
        conn.close()
    return result

def add_user_bot(user):
    users_db.add_or_update_user(user)

def get_force_channels():
    rows = execute_query("SELECT id, name, invite_link FROM channels;", fetchall=True)
    return [{"db_id": r[0], "name": r[1], "invite": r[2]} for r in rows]

def add_channel(name, invite_link):
    # نعتمد على SERIAL لتوليد id الداخلي كما في المخطط الخاص بك
    query = "INSERT INTO channels (name, invite_link) VALUES (%s, %s);"
    execute_query(query, (name, invite_link), commit=True)

def delete_channel(db_id):
    execute_query("DELETE FROM channels WHERE id = %s;", (db_id,), commit=True)

def get_all_users():
    return users_db.get_active_users()

def log_broadcast(message_text):
    query = "INSERT INTO broadcasts (message_preview, message) VALUES (%s, %s) RETURNING id;"
    preview = message_text[:50] + "..." if len(message_text) > 50 else message_text
    result = execute_query(query, (preview, message_text), fetch=True, commit=True)
    return result[0] if result else None

def update_broadcast_stats(broadcast_id, total, success, failed):
    query = "UPDATE broadcasts SET total_users = %s, success_count = %s, failed_count = %s WHERE id = %s;"
    execute_query(query, (total, success, failed, broadcast_id), commit=True)

def log_broadcast_receiver(broadcast_id, user_id, status, error_msg=None):
    query = "INSERT INTO broadcast_receivers (broadcast_id, user_id, status, error_message) VALUES (%s, %s, %s, %s);"
    execute_query(query, (broadcast_id, user_id, status, error_msg), commit=True)

def deactivate_user(user_id):
    users_db.deactivate_user(user_id)

# ══════════════════════════════════════════
#              الدوال المساعدة
# ══════════════════════════════════════════

def is_admin(user_id: int) -> bool:
    return str(user_id) == str(ADMIN_ID)

def extract_telegram_id(invite_link):
    # استخراج @username من الرابط للاعتماد عليه كمعرف للقناة في API تليجرام
    if "t.me/" in invite_link:
        return "@" + invite_link.split("t.me/")[1].split("/")[0].replace("+", "")
    return invite_link

def check_subscriptions(user_id: int) -> list:
    if is_admin(user_id):
        return []

    now = time()
    if user_id in verified_cache and (now - verified_cache[user_id] < 240):
        return []

    channels = get_force_channels()
    not_subscribed = []
    VALID_STATUSES = ['member', 'administrator', 'creator']

    conn = get_db_connection()
    cur = conn.cursor()

    for ch in channels:
        telegram_id = extract_telegram_id(ch['invite'])
        try:
            member = bot.get_chat_member(telegram_id, user_id)
            if member.status in VALID_STATUSES:
                cur.execute("""
                    INSERT INTO user_channels (user_id, channel_id)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id, channel_id) DO NOTHING;
                """, (user_id, ch['db_id']))
            else:
                not_subscribed.append(ch)

        except telebot.apihelper.ApiTelegramException as e:
            error_text = e.description.lower()
            if "user not found" in error_text:
                not_subscribed.append(ch)
            else:
                not_subscribed.append(ch)
        except Exception:
            not_subscribed.append(ch)

    conn.commit()
    cur.close()
    conn.close()

    if not not_subscribed:
        verified_cache[user_id] = now

    return not_subscribed

# ══════════════════════════════════════════
#              لوحات المفاتيح
# ══════════════════════════════════════════

def main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("📚 المكتبة", "🌌 شبكة سديم", "❓ ما هي شبكة سديم؟", 
               "👨‍💻 المطور", "📩 تواصل مع المالك", "🆘 الدعم", "📋 عن سديم", "💻 قنوات لتعلم البرمجة", "📚 قنوات أدبية")
    return markup

def admin_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("📢 إضافة قناة إجبارية", "🗑 حذف قناة إجبارية", "📋 قائمة القنوات", 
               "📣 إرسال إذاعة", "📊 إحصائيات", "👥 المستخدمون", "📖 رواية اليوم")
    markup.add("🔙 الرئيسية")
    return markup

def exit_chat_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add("❌ إنهاء المحادثة")
    return markup

# قوائم التحقق لمنع التداخل
USER_BUTTONS = ["📚 المكتبة", "🌌 شبكة سديم", "❓ ما هي شبكة سديم؟", "👨‍💻 المطور", "📩 تواصل مع المالك", "🆘 الدعم", "📋 عن سديم", "🔙 الرئيسية", "❌ إلغاء", "💻 قنوات لتعلم البرمجة", "📚 قنوات أدبية"]
ADMIN_BUTTONS = ["📢 إضافة قناة إجبارية", "🗑 حذف قناة إجبارية", "📋 قائمة القنوات", "📣 إرسال إذاعة", "📊 إحصائيات", "👥 المستخدمون", "📖 رواية اليوم", "🔙 الرئيسية", "❌ إلغاء"]

# ═════════════════════════════════════════
#         المعالجات (Handlers)
# ══════════════════════════════════════════

@bot.message_handler(commands=['start', 'help'])
def start(message):
    user_id = message.from_user.id 
    add_user_bot(message.from_user) 
    
    # تفريغ حالة المستخدم إن وجدت
    user_states.pop(user_id, None)

    missing = check_subscriptions(user_id)
    if missing:
        markup = types.InlineKeyboardMarkup()
        for ch in missing: 
            markup.add(types.InlineKeyboardButton(text=ch['name'], url=ch['invite']))
        markup.add(types.InlineKeyboardButton("✅ تحققت من اشتراكي", callback_data="check_sub"))
        bot.send_message(user_id, "⚠️ للاستمرار، يرجى الاشتراك في القنوات التالية:", reply_markup=markup)
        return

    if is_admin(user_id):
        bot.send_message(user_id, "👑 أهلاً بك في لوحة تحكم سديم", reply_markup=admin_keyboard())
    else:
        bot.send_message(user_id, "🌌 مرحباً بك في عالم سديم الرقمي", reply_markup=main_keyboard())

@bot.message_handler(func=lambda m: m.text == "🔙 الرئيسية")
def go_home(message):
    start(message)

@bot.message_handler(func=lambda m: m.text == "❌ إلغاء")
def cancel_action(message):
    user_states.pop(message.from_user.id, None)
    bot.send_message(message.chat.id, "❌ تم إلغاء العملية الحالية.", 
                     reply_markup=admin_keyboard() if is_admin(message.from_user.id) else main_keyboard())

@bot.message_handler(func=lambda m: m.text == "❌ إنهاء المحادثة")
def exit_chat_action(message):
    user_states.pop(message.from_user.id, None)
    bot.send_message(message.chat.id, "✅ تم إنهاء جلسة التواصل مع المالك. عودة للقائمة الرئيسية.", reply_markup=main_keyboard())

# 1. معالجات الأدمن
@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text in ADMIN_BUTTONS)
def admin_buttons_handler(message):
    channels = get_force_channels()

    if message.text == "📢 إضافة قناة إجبارية":
        user_states[message.from_user.id] = 'waiting_ch_name'
        bot.send_message(message.chat.id, "📥 أرسل اسم القناة لعرضه في الأزرار:", 
                         reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("❌ إلغاء"))
    
    elif message.text == "📣 إرسال إذاعة":
        user_states[message.from_user.id] = 'waiting_broadcast_msg'
        bot.send_message(message.chat.id, "📥 أرسل الرسالة التي تريد تعميمها على جميع المستخدمين:", 
                         reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("❌ إلغاء"))
    
    elif message.text == "📊 إحصائيات":
        total, active = users_db.get_users_count()
        riyadh = pytz.timezone("Asia/Riyadh")
        bot.send_message(
            message.chat.id,
            f"📊 إحصائيات سديم:\n👥 إجمالي المستخدمين: {total}\n👥 المستخدمين النشطين: {active}\n📢 القنوات الإجبارية: {len(channels)}\n🕐 جدول رواية اليوم: {DAILY_NOVEL_HOUR:02d}:{DAILY_NOVEL_MINUTE:02d} (بتوقيت الرياض)",
            reply_markup=admin_keyboard(),
        )

    elif message.text == "👥 المستخدمون":
        total, active = users_db.get_users_count()
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("📋 قائمة المستخدمين (1-20)", callback_data="users_list_1"))
        markup.add(types.InlineKeyboardButton("🔍 بحث بـ ID", callback_data="users_search_prompt"))
        markup.add(types.InlineKeyboardButton("📥 تصدير JSON", callback_data="users_export"))
        bot.send_message(
            message.chat.id,
            f"👥 إدارة المستخدمين:\nمجموع المستخدمين: {total}\nالنشطون: {active}\n\nاختر الإجراء:",
            reply_markup=markup,
        )

    elif message.text == "📖 رواية اليوم":
        history = daily_novel_svc.get_history()
        last_entry = history[-1] if history else None
        if last_entry:
            book_url = daily_novel_svc._build_book_url(last_entry["book_id"])
            text = (
                f"📖 رواية اليوم — الإعدادات\n\n"
                f"🕐 وقت الإرسال: {DAILY_NOVEL_HOUR:02d}:{DAILY_NOVEL_MINUTE:02d} (بتوقيت الرياض)\n"
                f"📚 آخر رواية أُرسلت: {last_entry['title']}\n"
                f"📅 تم الإرسال: {last_entry['sent_at']}\n"
                f"✅ نجاح: {last_entry['success']}  ❌ فشل: {last_entry['failed']}\n"
                f"🔗 الرابط: {book_url}"
            )
        else:
            text = (
                f"📖 رواية اليوم — الإعدادات\n\n"
                f"🕐 وقت الإرسال: {DAILY_NOVEL_HOUR:02d}:{DAILY_NOVEL_MINUTE:02d} (بتوقيت الرياض)\n"
                f"📭 لم يتم إرسال أي رواية بعد."
            )
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("📤 إرسال الآن", callback_data="daily_send_now"))
        markup.add(types.InlineKeyboardButton("📜 سجل الإرسالات", callback_data="daily_history"))
        bot.send_message(message.chat.id, text, reply_markup=markup)

    elif message.text == "📋 قائمة القنوات":
        if not channels:
            bot.send_message(message.chat.id, "📭 القائمة فارغة حالياً.")
        else:
            text = "📋 القنوات المضافة:\n" + "\n".join([f"- {c['name']} (ID: {c['db_id']})" for c in channels])
            bot.send_message(message.chat.id, text)

    elif message.text == "🗑 حذف قناة إجبارية":
        if not channels:
            bot.send_message(message.chat.id, "📭 لا توجد قنوات لحذفها.")
            return
        markup = types.InlineKeyboardMarkup()
        for ch in channels:
            markup.add(types.InlineKeyboardButton(text=ch['name'], callback_data=f"del_ch_{ch['db_id']}"))
        bot.send_message(message.chat.id, "🗑 اختر القناة التي تريد حذفها:", reply_markup=markup)

# 2. معالجات المستخدم
@bot.message_handler(func=lambda m: not is_admin(m.from_user.id) and m.text in USER_BUTTONS)
def user_buttons_handler(message):
    user_id = message.from_user.id
    
    if message.text == "📩 تواصل مع المالك":
        user_states[user_id] = 'chat_with_owner'
        bot.send_message(user_id, "✍️ أنت الآن في وضع التواصل المباشر. اكتب رسالتك وسيتم إرسالها لصلاح فوراً.\nللخروج اضغط على 'إنهاء المحادثة'.", reply_markup=exit_chat_keyboard())
    
    elif message.text == "🆘 الدعم":
        bot.send_message(user_id, "🆘 الدعم متاح على مدار الساعة!\n📧 البريد: admin@sadim.com\n🤖 بوت الدعم: @SADIM_Sbot")

    elif message.text == "📚 المكتبة":
        books = Library.get_all_books()
        if not books:
            bot.reply_to(message, "⚠️ لا توجد كتب حالياً في المكتبة.")
            return
        markup = types.InlineKeyboardMarkup(row_width=1)
        for b in books:
            markup.add(types.InlineKeyboardButton(text=f"📖 {b.get('title', 'بدون عنوان')}", callback_data=f"get_book_{b.get('id')}"))
        bot.send_message(user_id, f"📚 المكتبة — لدينا {len(books)} كتاب متاح.\nاختر الرواية التي تود تحميلها:", reply_markup=markup)
    
    elif message.text == "🌌 شبكة سديم":
        bot.send_message(user_id, "🌌 شبكة سديم ليست مجرد منصة، بل نظام رقمي يجمع بين المعرفة، التقنية، والمحتوى الأدبي في مساحة واحدة.\n\n"
"تُبنى على فكرة الربط بين المحتوى والبرمجة، حيث تتكامل القنوات والمكتبة والخدمات الرقمية ضمن هيكل واحد قابل للتوسع.\n\n"
"🔗 الموقع: https://sadim.cloud")

    elif message.text == "❓ ما هي شبكة سديم؟":
        bot.send_message(user_id, "🌌 شبكة سديم تُبنى على فكرة واحدة:\n"
"تحويل المحتوى من منشورات متفرقة إلى نظام رقمي حيّ يتفاعل ويتوسع.\n\n"
"كل قناة، كتاب، وخدمة هي جزء من هيكل أكبر قابل للنمو.:\n🔗 https://sadim.cloud/about")

    elif message.text == "👨‍💻 المطور":
        bot.send_message(user_id, "👨‍💻 المطوّر: صلاح\n\n"
"مطور مستقل يعمل على بناء أنظمة رقمية متكاملة تجمع بين البرمجة، إدارة المحتوى، وأتمتة الخدمات.\n\n"
"يركّز حالياً على تطوير الباك-إند باستخدام Python وPostgreSQL، وبناء أنظمة قابلة للتوسع مثل البوتاتو المواقع و التطبيقات والمنصات الرقمية.\n\n" 
"🔗 الملف الشخصي: https://www.sadim.cloud/admin/profile/view")

    elif message.text in ["📋 عن سديم", "💻 قنوات لتعلم البرمجة", "📚 قنوات أدبية"]:
        # اختصاراً للردود الثابتة
        responses = {
            "📋 عن سديم": "شبكة سديم هي منصة رقمية متكاملة...",
            "💻 قنوات لتعلم البرمجة": "https://t.me/python_1I",
            "📚 قنوات أدبية": "https://t.me/hx5cb"
        }
        bot.send_message(user_id, responses[message.text])

# 3. محرك الرسائل للأدمن (ردود وحالات)
@bot.message_handler(func=lambda m: is_admin(m.from_user.id), content_types=['text', 'photo', 'voice', 'document'])
def admin_catch_all(message):
    state = user_states.get(message.from_user.id)
    
    # حالة إضافة قناة (الخطوة 1: الاسم)
    if state == 'waiting_ch_name':
        user_states[message.from_user.id] = {'step': 'waiting_ch_link', 'name': message.text}
        bot.send_message(message.chat.id, "✅ حسناً، أرسل الآن رابط الدعوة للقناة (يبدأ بـ https://t.me/):")
        return
        
    # حالة إضافة قناة (الخطوة 2: الرابط وحفظ في القاعدة)
    elif isinstance(state, dict) and state.get('step') == 'waiting_ch_link':
        ch_name = state['name']
        invite_link = message.text
        add_channel(ch_name, invite_link)
        user_states.pop(message.from_user.id, None)
        bot.send_message(message.chat.id, "🎊 تمت إضافة القناة بنجاح للقاعدة!", reply_markup=admin_keyboard())
        return

    # حالة الإذاعة
    if state == 'waiting_broadcast_msg':
        bot.send_message(message.chat.id, "⏳ جاري إرسال الإذاعة...", reply_markup=admin_keyboard())
        user_states.pop(message.from_user.id, None)
        
        broadcast_id = log_broadcast(message.text)
        users = get_all_users()
        success, failed = 0, 0
        
        for u in users:
            uid = u['id']
            try:
                bot.send_message(uid, message.text)
                log_broadcast_receiver(broadcast_id, uid, 'success')
                success += 1
            except Exception as e:
                err = str(e).lower()
                if "blocked" in err or "privacy" in err or "not found" in err:
                    deactivate_user(uid)
                log_broadcast_receiver(broadcast_id, uid, 'failed', str(e))
                failed += 1
                
        update_broadcast_stats(broadcast_id, len(users), success, failed)
        bot.send_message(message.chat.id, f"✅ اكتملت الإذاعة!\nنجاح: {success}\nفشل: {failed}")
        return

    # حالة البحث عن مستخدم بواسطة المعرف
    if state == "waiting_user_search":
        try:
            uid = int(message.text.strip())
        except ValueError:
            bot.send_message(message.chat.id, "❌ الرجاء إرسال رقم المعرف بشكل صحيح.")
            return
        user = users_db.get_user(uid)
        user_states.pop(message.from_user.id, None)
        if not user:
            bot.send_message(message.chat.id, f"🔍 لم يُعثر على مستخدم بالمعرف `{uid}`.", parse_mode="Markdown", reply_markup=admin_keyboard())
        else:
            _send_user_detail(message.chat.id, user)

    # معالجة الردود المباشرة على المستخدمين
    if message.reply_to_message:
        target_uid = forwarded_msgs.get(message.reply_to_message.message_id)
        if target_uid:
            try:
                if message.content_type == 'text':
                    bot.send_message(target_uid, f"📩 **رد من صلاح:**\n\n{message.text}", parse_mode="Markdown")
                else:
                    bot.copy_message(target_uid, message.chat.id, message.message_id, caption="📩 **رد من صلاح**", parse_mode="Markdown")
                bot.send_message(message.chat.id, "✅ تم إرسال الرد.")
            except:
                bot.send_message(message.chat.id, "❌ فشل الإرسال (ربما قام المستخدم بحظر البوت).")
        else:
            bot.send_message(message.chat.id, "⚠️ لم أتعرف على صاحب هذه الرسالة بالذاكرة المؤقتة.")

# 4. محرك الرسائل للمستخدم (التوجيه)
@bot.message_handler(func=lambda m: not is_admin(m.from_user.id), content_types=['text', 'photo', 'voice', 'document'])
def user_catch_all(message):
    users_db.touch_user(message.from_user.id)
    if check_subscriptions(message.from_user.id):
        start(message)
        return

    # التحقق مما إذا كان المستخدم في وضع التواصل مع المالك
    if user_states.get(message.from_user.id) == 'chat_with_owner':
        try:
            sent = bot.forward_message(ADMIN_ID, message.chat.id, message.message_id)
            forwarded_msgs[sent.message_id] = message.chat.id
            bot.reply_to(message, "🚀 تم الإرسال.")
        except:
            bot.send_message(message.chat.id, "⚠️ حدث خطأ أثناء إرسال رسالتك.")
    else:
        bot.send_message(message.chat.id, "⚠️ عذراً، لا يمكنني معالجة رسالتك. اضغط على 'تواصل مع المالك' إذا كنت تريد إرسال رسالة له.")

# ═════════════════════════════════════════
#         استدعاءات الأزرار (Callbacks)
# ══════════════════════════════════════════

@bot.callback_query_handler(func=lambda call: call.data.startswith("del_ch_"))
def handle_delete_channel(call):
    ch_db_id = call.data.replace("del_ch_", "")
    delete_channel(ch_db_id)
    bot.answer_callback_query(call.id, "✅ تم حذف القناة من قاعدة البيانات", show_alert=True)
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass

@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def callback_verify(call):
    user_id = call.from_user.id 
    verified_cache.pop(user_id, None)
    missing = check_subscriptions(user_id)
    
    if missing:
        bot.answer_callback_query(call.id, "❌ لم تشترك في كافة القنوات بعد!", show_alert=True)
    else:
        bot.answer_callback_query(call.id, "✅ شكراً لاشتراكك!")
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        if is_admin(user_id):
            bot.send_message(user_id, "👑 أهلاً بك في لوحة تحكم سديم", reply_markup=admin_keyboard())
        else:
            bot.send_message(user_id, "🌌 مرحباً بك في عالم سديم الرقمي", reply_markup=main_keyboard())

@bot.callback_query_handler(func=lambda call: call.data.startswith('get_book_'))
def handle_book_sending(call):
    book_id = call.data.replace('get_book_', '')
    book = Library.get_book_id(book_id) 
    
    if not book:
        bot.answer_callback_query(call.id, "❌ عذراً، لم يتم العثور على بيانات الكتاب.")
        return

    bot.answer_callback_query(call.id, "⏳ جاري تجهيز الملف...")
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
    
    title = book.get('title', 'بدون عنوان')
    pdf_path = os.path.join(UPLOAD_FOLDER, book.get('pdf_path', ''))
    cover_path = os.path.join(UPLOAD_FOLDER, book.get('cover_path', ''))
    user_id = call.from_user.id

    if os.path.exists(cover_path):
        with open(cover_path, 'rb') as cover:
            bot.send_photo(user_id, cover, caption=f"📖 {title}")

    if os.path.exists(pdf_path):
        with open(pdf_path, 'rb') as pdf:
            bot.send_document(user_id, pdf)
    else:
        bot.send_message(user_id, f"❌ عذراً، ملف الـ PDF غير متوفر حالياً.")


# ═════════════════════════════════════════
#         مدى إدارة المستخدمين والرواية اليوم
# ═════════════════════════════════════════

_users_per_page = 20


def _format_user_entry(u):
    status = "✅ نشط" if u.get("is_active") else "🚫 غير نشط"
    joined = u.get("joined_at") or "غير محدد"
    seen = u.get("last_seen") or "لم يُسجّل"
    return f"`{u['id']}` — {u.get('first_name') or '—'} @{u.get('username') or '—'} — {status}"


@bot.callback_query_handler(func=lambda call: call.data.startswith("users_list_"))
def callback_users_list(call):
    try:
        page = int(call.data.split("_")[-1])
    except (ValueError, IndexError):
        page = 1
    all_users = users_db.get_all_users()
    total_pages = max(1, (len(all_users) + _users_per_page - 1) // _users_per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * _users_per_page
    end = start + _users_per_page
    chunk = all_users[start:end]

    text = f"📋 قائمة المستخدمين (ص {page} من {total_pages}):\n\n"
    text += "\n".join(_format_user_entry(u) for u in chunk)
    text += f"\n\n📊 إجمالي: {len(all_users)}"

    markup = types.InlineKeyboardMarkup(row_width=2)
    if page > 1:
        markup.add(types.InlineKeyboardButton("⬅️ السابق", callback_data=f"users_list_{page - 1}"))
    if page < total_pages:
        markup.add(types.InlineKeyboardButton("➡️ التالي", callback_data=f"users_list_{page + 1}"))
    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
    except Exception:
        bot.send_message(call.message.chat.id, text, reply_markup=markup)

    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data == "users_search_prompt")
def callback_users_search_prompt(call):
    user_states[call.from_user.id] = "waiting_user_search"
    bot.edit_message_text(
        "🔍 أرسل معرف المستخدم (الرقم) الذي تريد البحث عنه:",
        call.message.chat.id, call.message.message_id,
        reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("❌ إلغاء", callback_data="users_search_cancel")),
    )
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data == "users_search_cancel")
def callback_users_search_cancel(call):
    user_states.pop(call.from_user.id, None)
    bot.edit_message_text("✅ تم إلغاء البحث.", call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id)


def _send_user_detail(chat_id, user):
    status = "✅ نشط" if user.get("is_active") else "🚫 غير نشط"
    joined = user.get("joined_at") or "غير محدد"
    seen = user.get("last_seen") or "لم يُسجّل"
    text = (
        f"👤 ملف المستخدم:\n"
        f"🆔 المعرف: `{user['id']}`\n"
        f"👤 الاسم: {user.get('first_name') or '—'}\n"
        f"📎 اليوزرنيم: @{user.get('username') or '—'}\n"
        f"حالة: {status}\n"
        f"📅 انضم: {joined}\n"
        f"🕐 آخر نشاط: {seen}"
    )
    markup = types.InlineKeyboardMarkup()
    if user.get("is_active"):
        markup.add(types.InlineKeyboardButton("🚫 إيقاف التفعيل", callback_data=f"users_toggle_{user['id']}"))
    else:
        markup.add(types.InlineKeyboardButton("✅ تفعيل", callback_data=f"users_toggle_{user['id']}"))
    bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")


@bot.callback_query_handler(func=lambda call: call.data.startswith("users_toggle_"))
def callback_users_toggle(call):
    try:
        uid = int(call.data.split("_")[-1])
    except ValueError:
        bot.answer_callback_query(call.id, "❌ معرف غير صالح", show_alert=True)
        return
    user = users_db.get_user(uid)
    if not user:
        bot.answer_callback_query(call.id, "❌ المستخدم غير موجود", show_alert=True)
        return
    if user.get("is_active"):
        users_db.deactivate_user(uid)
        bot.answer_callback_query(call.id, "✅ تم إيقاف تفعيل المستخدم", show_alert=True)
    else:
        users_db.reactivate_user(uid)
        bot.answer_callback_query(call.id, "✅ تم تفعيل المستخدم", show_alert=True)
    # Re-show updated detail
    bot.delete_message(call.message.chat.id, call.message.message_id)


@bot.callback_query_handler(func=lambda call: call.data == "users_export")
def callback_users_export(call):
    all_users = users_db.get_all_users()
    total, active = users_db.get_users_count()
    summary = {
        "total_users": total,
        "active_users": active,
        "exported_at": datetime.now(timezone.utc).astimezone().isoformat(),
    }
    data = {"summary": summary, "users": all_users}
    text = json.dumps(data, indent=2, ensure_ascii=False)
    # Send as file to avoid hitting message limits
    import io
    file_obj = io.StringIO(text)
    file_obj.seek(0)
    bot.send_document(call.message.chat.id, (io.BytesIO(text.encode("utf-8")), "users_export.json"),
                      caption=f"📥 تم تصدير {total} مستخدم.")
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data == "daily_send_now")
def callback_daily_send_now(call):
    bot.answer_callback_query(call.id, "⏳ جاري إرسال الرواية الآن...")
    result = daily_novel_svc.send_daily_novel_now(bot)
    if result and "skipped" in result:
        bot.send_message(call.message.chat.id, f"⚠️ تم التخطيط: {result['reason']}")
    elif result:
        book_url = daily_novel_svc._build_book_url(result["book_id"])
        bot.send_message(
            call.message.chat.id,
            f"✅ أرسلت «{result['title']}» إلى {result['success']} مستخدم.\n"
            f"❌ فشل: {result['failed']}\n🔗 {book_url}"
        )
    else:
        bot.send_message(call.message.chat.id, "❌ لم يتم العثور على أي رواية للإرسال.")


@bot.callback_query_handler(func=lambda call: call.data == "daily_history")
def callback_daily_history(call):
    history = daily_novel_svc.get_history()
    if not history:
        bot.answer_callback_query(call.id, "📭 لا توجد سجلات بعد", show_alert=True)
        return
    lines = []
    for e in reversed(history[-10:]):
        lines.append(
            f"📚 {e['title']}\n"
            f"  📅 {e['sent_at']}\n"
            f"  ✅ {e['success']}  ❌ {e['failed']}"
        )
    text = "📜 آخر 10 إرسالات:\n\n" + "\n\n".join(lines)
    bot.send_message(call.message.chat.id, text)
    bot.answer_callback_query(call.id)


# Module-level startup: ensure the daily-novel scheduler is registered
# whenever this module is imported (covers both __main__ and bot_runner paths).
try:
    daily_novel_svc.ensure_scheduler_running(bot, DAILY_NOVEL_HOUR, DAILY_NOVEL_MINUTE)
except Exception as e:
    print(f"⚠️ لم يتم بدء جدول رواية اليوم: {e}")


if __name__ == "__main__":
    print("--- SADIM NETWORK SYSTEM ONLINE ---")
    bot.infinity_polling(skip_pending=True)