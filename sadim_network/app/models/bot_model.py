#sadim_network/app/models/bot_model.py
from db.sadim_db import get_db_connection
from datetime import datetime


class Bot():
    def __init__(self, id=None, user_id=None, bot_token=None, channel=None, is_active=None, created_at=None):
        self.id = id
        self.user_id = user_id
        self.bot_token = bot_token
        self.channel = channel
        self.is_active = is_active
        self.created_at = created_at or datetime.now()

    def add(self):
        '''''adds new bot to the database and returns the new bot's id.
         اضافة بوت جديد إلى قاعدة البيانات وإرجاع معرف البوت الجديد.'''''
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO bots (user_id, bot_token, channel, is_active, created_at)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
        ''', (self.user_id, self.bot_token, self.channel, self.is_active, self.created_at))
        bot_id = cur.fetchone()[0]
        conn.commit()
        conn.close()
        cur.close()
        return bot_id
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
        '''''Retrieves a bot from the database by its token.
        استرجاع بوت من قاعدة البيانات باستخدام رمزه.
        '''
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM bots WHERE bot_token = %s AND is_active = TRUE", (token,))
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