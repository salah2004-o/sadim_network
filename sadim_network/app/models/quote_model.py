#sadim_network/app/models/quote_model.py
from db.sadim_db import get_db_connection
from datetime import datetime


class Quote:
    def __init__(
        self,
        id=None,
        bot_id=None,
        text=None,
        author=None,
        published=False,
        created_at=None
    ):
        self.id = id
        self.bot_id = bot_id
        self.text = text
        self.author = author
        self.published = published
        self.created_at = created_at

    # ---------- CREATE ----------
    def add_to_db(self):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO quotes (bot_id, text, author, published, created_at)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id;
        """, (
            self.bot_id,
            self.text,
            self.author,
            self.published,
            datetime.now()
        ))
        quote_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return quote_id

    # ---------- GET NEXT UNPUBLISHED ----------
    @staticmethod
    def get_next(bot_id):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM quotes
            WHERE bot_id=%s AND published=FALSE
            ORDER BY id ASC
            LIMIT 1;
        """, (bot_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return Quote._row_to_quote(row)

    # ---------- MARK AS PUBLISHED ----------
    @staticmethod
    def mark_published(quote_id):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE quotes SET published=TRUE WHERE id=%s;",
            (quote_id,)
        )
        conn.commit()
        cur.close()
        conn.close()
        return True

    # ---------- GET ALL BY BOT ----------
    @staticmethod
    def get_all_by_bot(bot_id):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM quotes WHERE bot_id=%s ORDER BY id ASC;", (bot_id,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [Quote._row_to_quote(row) for row in rows]

    # ---------- INTERNAL MAPPER ----------
    @staticmethod
    def _row_to_quote(row):
        if not row:
            return None
        return Quote(
            id=row[0],
            bot_id=row[1],
            text=row[2],
            author=row[3],
            published=row[4],
            created_at=row[5]
        )