# ميزة "التواصل عبر البوت": أي رسالة عادية توصل لصاحب البوت عبر تيليجرام مباشرة،
# ويرد صاحب البوت بالرد على الرسالة المُعاد توجيهها فترجع للمرسل الأصلي —
# حتى لو خصوصية صاحب البوت تمنع استقبال رسائل مباشرة من الغرباء (لأنه هو نفسه من بدأ المحادثة مع بوته).
from models.bot_model import Bot

FEATURES = [
    {"key": "contact_owner", "label": "التواصل عبر البوت",
     "description": "أي رسالة عادية يرسلها مستخدم توصل مباشرة لصاحب البوت، ويقدر يرد عليها من تيليجرامه.",
     "help_line": None},
]

# {(bot_id, forwarded_message_id): original_sender_chat_id} — بالذاكرة، يكفي لعمر تشغيل العملية
_forwarded_msgs = {}


def register(bot, bot_id, enabled_features):
    if "contact_owner" not in enabled_features:
        return

    @bot.message_handler(commands=['claim'])
    def claim(message):
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            bot.reply_to(message, "⚠️ استخدم: /claim <الكود> — الكود موجود بصفحة إدارة البوت بالموقع.")
            return

        code = parts[1].strip()
        bot_row = Bot.get_by_id_from_user(bot_id)
        if not bot_row or not bot_row.claim_code or bot_row.claim_code.upper() != code.upper():
            bot.reply_to(message, "❌ الكود غير صحيح.")
            return

        # مهم: البوت مسموح يُربط مرة وحدة بس. لو حد ثاني عرف نفس الكود (تسريب، لقطة شاشة...)
        # بعد ما البوت مرتبط فعلاً، ما نسمح له يسحب الملكية من المالك الحالي — لازم صاحب
        # الحساب الحقيقي (تسجيل دخول بالموقع) يفك الربط أولاً من صفحة إدارة البوت.
        if bot_row.owner_telegram_id:
            bot.reply_to(message, "❌ البوت مرتبط بالفعل بحساب مالك. لإعادة الربط بحساب مختلف، سجّل دخولك بموقع شبكة سديم وألغِ الربط من صفحة إدارة البوت أولاً.")
            return

        linked = Bot.set_owner_telegram_id(bot_id, message.from_user.id)
        if linked:
            bot.reply_to(message, "✅ تم تفعيل استقبال رسائل التواصل على حسابك بنجاح. أي رسالة يرسلها مستخدم بتوصلك هنا.")
        else:
            bot.reply_to(message, "❌ البوت مرتبط بالفعل بحساب مالك.")

    @bot.message_handler(func=lambda m: m.text and not m.text.startswith('/') and not m.text.strip().lower().startswith('http'))
    def relay(message):
        bot_row = Bot.get_by_id_from_user(bot_id)
        owner_id = bot_row.owner_telegram_id if bot_row else None
        if not owner_id:
            return  # صاحب البوت ما فعّل /claim بعد — نتجاهل بصمت

        # رد صاحب البوت على رسالة مُعاد توجيهها -> رجّعه للمرسل الأصلي
        if message.chat.id == owner_id and message.reply_to_message:
            target_chat_id = _forwarded_msgs.get((bot_id, message.reply_to_message.message_id))
            if target_chat_id:
                try:
                    bot.send_message(target_chat_id, f"📩 رد من صاحب البوت:\n\n{message.text}")
                    bot.reply_to(message, "✅ تم إرسال الرد.")
                except Exception:
                    bot.reply_to(message, "⚠️ تعذر إرسال الرد (يبدو المستخدم حظر البوت).")
            return

        # رسالة عادية من مستخدم -> إعادة توجيه لصاحب البوت مع بيانات تعريفية صريحة
        # (البيانات تُقرأ تلقائياً من تيليجرام، ما تحتاج نطلبها من المستخدم — لكن نكتبها كنص
        # صريح بدل الاعتماد فقط على ترويسة "Forwarded from" لأن المستخدم يقدر يخفيها من إعدادات الخصوصية)
        sender = message.from_user
        username_line = f"@{sender.username}" if sender.username else "بدون يوزرنيم"
        header = (
            f"📩 رسالة جديدة من {sender.first_name or 'مستخدم'}\n"
            f"اليوزرنيم: {username_line}\n"
            f"الأيدي: {sender.id}"
        )
        try:
            header_msg = bot.send_message(owner_id, header)
            forwarded = bot.forward_message(owner_id, message.chat.id, message.message_id)
            _forwarded_msgs[(bot_id, header_msg.message_id)] = message.chat.id
            _forwarded_msgs[(bot_id, forwarded.message_id)] = message.chat.id
            bot.reply_to(message, "📨 تم إرسال رسالتك لصاحب البوت، بيوصلك رد قريباً.")
        except Exception:
            pass  # صاحب البوت ما فعّل الاستقبال أو حظر البوت — تجاهل بصمت
