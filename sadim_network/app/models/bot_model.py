#sadim_network/app/models/bot_model.py
import random
import string
import requests
from db.sadim_db import get_db_connection
from datetime import datetime


def _generate_claim_code(length=6):
    return ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(length))


class Bot():
    def __init__(self, id=None, user_id=None, bot_token=None, channel=None, is_active=None,
                 created_at=None, last_announced_book_id=None, claim_code=None, owner_telegram_id=None,
                 telegram_username=None, telegram_first_name=None):
        self.id = id
        self.user_id = user_id
        self.bot_token = bot_token
        self.channel = channel
        self.is_active = is_active
        self.created_at = created_at or datetime.now()
        self.last_announced_book_id = last_announced_book_id
        self.claim_code = claim_code
        self.owner_telegram_id = owner_telegram_id
        self.telegram_username = telegram_username
        self.telegram_first_name = telegram_first_name

    def add(self):
        '''''adds new bot to the database and returns the new bot's id.
         اضافة بوت جديد إلى قاعدة البيانات وإرجاع معرف البوت الجديد.'''''
        if not self.claim_code:
            self.claim_code = _generate_claim_code()
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO bots (user_id, bot_token, channel, is_active, created_at, claim_code)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
        ''', (self.user_id, self.bot_token, self.channel, self.is_active, self.created_at, self.claim_code))
        bot_id = cur.fetchone()[0]
        conn.commit()
        conn.close()
        cur.close()
        return bot_id

    @staticmethod
    def set_owner_telegram_id(bot_id, telegram_id):
        """يربط تيليجرام صاحب البوت — بس لو ما كان مرتبط من قبل (شرط SQL ذري يمنع
        أي شخص ثاني يعرف نفس claim_code من سرقة الملكية لاحقاً، ويمنع أي Race Condition
        لو صار /claim من حسابين بنفس اللحظة تقريباً). يرجّع True لو نجح الربط فعلاً."""
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE bots SET owner_telegram_id = %s WHERE id = %s AND owner_telegram_id IS NULL",
            (telegram_id, bot_id)
        )
        linked = cur.rowcount > 0
        conn.commit()
        cur.close()
        conn.close()
        return linked

    @staticmethod
    def unlink_owner(bot_id):
        """يفك ربط صاحب البوت الحالي ويولّد كود مطالبة جديد (يُبطل القديم لو كان مكشوفاً/مسرّباً).
        مخصص لصفحة إدارة البوت فقط (محمية بتسجيل الدخول + التحقق من الملكية) — مو لتيليجرام."""
        new_code = _generate_claim_code()
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE bots SET owner_telegram_id = NULL, claim_code = %s WHERE id = %s",
            (new_code, bot_id)
        )
        conn.commit()
        cur.close()
        conn.close()
        return new_code

    @staticmethod
    def ensure_claim_code(bot_id):
        """يضمن وجود claim_code لأي بوت (مهم للبوتات اللي انربطت قبل إضافة هذي الميزة) — يرجع الكود."""
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT claim_code FROM bots WHERE id = %s", (bot_id,))
        row = cur.fetchone()
        code = row[0] if row else None
        if not code:
            code = _generate_claim_code()
            cur.execute("UPDATE bots SET claim_code = %s WHERE id = %s", (code, bot_id))
            conn.commit()
        cur.close()
        conn.close()
        return code

    @staticmethod
    def refresh_telegram_info(bot_id, bot_token):
        """يجيب اسم البوت ويوزرنيمه الحقيقيين من تيليجرام (getMe) ويحدّثهم بقاعدة البيانات."""
        try:
            r = requests.get(f"https://api.telegram.org/bot{bot_token}/getMe", timeout=5)
            data = r.json()
            if not (r.status_code == 200 and data.get("ok")):
                return False
        except Exception:
            return False

        result = data.get("result", {})
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE bots SET telegram_username = %s, telegram_first_name = %s WHERE id = %s",
            (result.get("username"), result.get("first_name"), bot_id)
        )
        conn.commit()
        cur.close()
        conn.close()
        return True
    @staticmethod
    def get_by_id(bot_id):
        """Retrieves a bot from the database by its ID.
        استرجاع بوت من قاعدة البيانات باستخدام معرفه.
        مع جميع البيانات و هذا مخصص للادمن فقط لعرض كل البوتات في لوحة الادمن
        """
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT id, user_id, bot_token, channel, is_active, created_at FROM bots WHERE id = %s', (bot_id,))
        bot_data = cur.fetchone()
        conn.close()
        cur.close()
        if bot_data:
            return Bot(*bot_data)
        return None
    
    @staticmethod
    def get_by_id_from_user(bot_id):
        """Retrieves a bot from the database by its ID.
        استرجاع بوت من قاعدة البيانات باستخدام معرفه.
        متاح لكل مستخدم فقط حتى يرى البوتات التي تم تفعيلها على المنصة و هذا مخصص لكل مستخدم لعرض بوتاته في لوحة المستخدم   
        """
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT * FROM bots WHERE id = %s', (bot_id,))
        bot_data = cur.fetchone()
        conn.close()
        cur.close()
        if bot_data:
            return Bot(*bot_data)
        return None

    @staticmethod
    def get_by_token(token):
        '''''Retrieves a bot from the database by its token (بغض النظر عن حالة التفعيل —
        تُستخدم لمنع تكرار نفس التوكن بأكثر من بوت، وبوت موقوف مؤقتاً يبقى "مستخدَم").
        استرجاع بوت من قاعدة البيانات باستخدام رمزه.
        '''
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM bots WHERE bot_token = %s", (token,))
        rwo = cur.fetchone()
        conn.close()
        cur.close()
        return Bot(*rwo) if rwo else None
    
    @staticmethod
    def get_by_user(user_id):
        '''''Retrieves all bots from the database by user id.
        استرجاع جميع البوتات من قاعدة البيانات باستخدام معرف المستخدم.
        '''
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM bots WHERE user_id = %s", (user_id,))
        rows = cur.fetchall()

        conn.close()
        cur.close()
        return [Bot(*row) for row in rows]
    
    @staticmethod
    def delete(bot_id):
        '''''Deletes a bot from the database by its ID.
        حذف بوت من قاعدة البيانات باستخدام معرفه.
        '''
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('DELETE FROM bots WHERE id = %s', (bot_id,))
        conn.commit()
        conn.close()
        cur.close()
    @staticmethod
    def update(bot_id, is_active):
        '''''Updates a bot's active status in the database by its ID.
        تحديث حالة تفعيل بوت في قاعدة البيانات باستخدام معرفه.
        '''
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('UPDATE bots SET is_active = %s WHERE id = %s', (is_active, bot_id))
        conn.commit()
        conn.close()
        cur.close()

    @staticmethod
    def row_to_bot(row):
        '''''Converts a database row to a Bot object.
        تحويل صف قاعدة البيانات إلى كائن بوت.
        '''
        if not row:
            return None
        
        return Bot(
            id=row[0],
            user_id=row[1],
            bot_token=row[2],
            channel=row[3],
            is_active=row[4],
            created_at=row[5]
        )

    @staticmethod
    def get_all():
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM bots ORDER BY created_at DESC")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [Bot(*row) for row in rows]

    @staticmethod
    def get_active_bots():
        """كل البوتات النشطة — تُستخدم من الجدولة (نشر الروايات بالقنوات)."""
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM bots WHERE is_active = TRUE")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [Bot(*row) for row in rows]

    @staticmethod
    def update_last_announced(bot_id, book_id):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE bots SET last_announced_book_id = %s WHERE id = %s", (book_id, bot_id))
        conn.commit()
        cur.close()
        conn.close()

    @staticmethod
    def get_all_with_owner():
        """كل البوتات مع اسم صاحب كل بوت — مخصص للوحة تحكم الأدمن."""
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT bots.id, bots.user_id, bots.bot_token, bots.channel,
                   bots.is_active, bots.created_at, users.username,
                   bots.telegram_username, bots.telegram_first_name
            FROM bots
            JOIN users ON bots.user_id = users.id
            ORDER BY bots.created_at DESC
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [
            {
                "id": r[0], "user_id": r[1], "bot_token": r[2], "channel": r[3],
                "is_active": r[4], "created_at": r[5], "username": r[6],
                "telegram_username": r[7], "telegram_first_name": r[8],
            }
            for r in rows
        ]