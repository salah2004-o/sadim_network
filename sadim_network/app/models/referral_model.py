#sadim_network/app/models/referral_model.py
# نظام الدعوة — رابط ?ref=<user_id> بدون توليد كود جديد (أبسط، صفر تعارض).
# المكافأة تعيد استخدام bot_limit_grants الموجود فعلاً: +1 بوت لمدة REWARD_DAYS يوم لكل دعوة ناجحة،
# نفس نقطة الدخول upsert() المصمَّمة أصلاً لتُستدعى من أي مصدر منح مستقبلي بدون تعديل منطقها.
from datetime import datetime, timedelta
from db.sadim_db import get_db_connection
from app.models.bot_limit_model import BotLimitGrant

REWARD_DAYS = 30
REWARD_BONUS = 1


class Referral:

    @staticmethod
    def record_and_reward(referrer_user_id, referred_user_id):
        """يُستدعى مرة واحدة فقط، فور نجاح تسجيل مستخدم جديد عبر رابط دعوة صالح.
        يرجّع True لو نجحت الإحالة والمكافأة، False لو فشلت (إحالة ذاتية، مُحال مسبقاً، أو referrer غير موجود)."""
        if not referrer_user_id or referrer_user_id == referred_user_id:
            return False

        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO referrals (referrer_user_id, referred_user_id, reward_days) VALUES (%s, %s, %s)",
                (referrer_user_id, referred_user_id, REWARD_DAYS),
            )
            conn.commit()
        except Exception:
            # UNIQUE على referred_user_id (مُحال مسبقاً) أو FK غير صالح (referrer وهمي) — فشل صامت آمن
            conn.rollback()
            cur.close()
            conn.close()
            return False
        cur.close()
        conn.close()

        current_limit = BotLimitGrant.get_effective_limit(referrer_user_id)
        if current_limit is None:
            return True  # المُحيل أصلاً بحد غير محدود — لا حاجة لمكافأة إضافية

        BotLimitGrant.upsert(
            referrer_user_id,
            bot_limit=current_limit + REWARD_BONUS,
            is_unlimited=False,
            expires_at=datetime.now() + timedelta(days=REWARD_DAYS),
        )
        return True

    @staticmethod
    def get_referral_count(user_id):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM referrals WHERE referrer_user_id = %s", (user_id,))
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        return count

    @staticmethod
    def get_referred_by(user_id):
        """يرجّع user_id الشخص اللي دعا هذا المستخدم، أو None لو سجّل بدون دعوة."""
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT referrer_user_id FROM referrals WHERE referred_user_id = %s", (user_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row[0] if row else None
