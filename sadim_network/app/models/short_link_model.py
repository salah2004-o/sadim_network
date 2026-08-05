import random
import string
from db.sadim_db import get_db_connection


def _generate_code(length=6):
    alphabet = string.ascii_letters + string.digits
    return ''.join(random.choice(alphabet) for _ in range(length))


class ShortLink:
    def __init__(self, id=None, code=None, original_url=None, bot_id=None, clicks=0, created_at=None):
        self.id = id
        self.code = code
        self.original_url = original_url
        self.bot_id = bot_id
        self.clicks = clicks
        self.created_at = created_at

    def add(self):
        """ينشئ كود فريد ويحفظ الرابط، يرجع الكود."""
        conn = get_db_connection()
        cur = conn.cursor()
        for _ in range(5):  # محاولات لتفادي تصادم الكود العشوائي (احتمال نادر جداً)
            code = _generate_code()
            cur.execute("SELECT 1 FROM short_links WHERE code = %s", (code,))
            if not cur.fetchone():
                break
        cur.execute(
            "INSERT INTO short_links (code, original_url, bot_id) VALUES (%s, %s, %s)",
            (code, self.original_url, self.bot_id)
        )
        conn.commit()
        cur.close()
        conn.close()
        self.code = code
        return code

    @staticmethod
    def get_by_code(code):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, code, original_url, bot_id, clicks, created_at FROM short_links WHERE code = %s", (code,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return ShortLink(*row) if row else None

    @staticmethod
    def increment_clicks(link_id):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE short_links SET clicks = clicks + 1 WHERE id = %s", (link_id,))
        conn.commit()
        cur.close()
        conn.close()
