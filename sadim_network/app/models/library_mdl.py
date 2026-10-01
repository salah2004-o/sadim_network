from db.sadim_db import get_db_connection
import psycopg2.extras
from datetime import datetime
import time

# القيم الافتراضية لكتب المكتبة الحالية (كلها لأجاثا كريستي) — تُعدَّل لكل كتاب من لوحة الإدارة
DEFAULT_AUTHOR = "أجاثا كريستي"
DEFAULT_GENRE = "رواية بوليسية"
GENRE_SUGGESTIONS = ("رواية بوليسية", "مجموعة قصصية", "مسرحية", "سيرة ذاتية")

# حدود فلتر الطول (عدد الصفحات)
LENGTH_BUCKETS = (("short", "قصيرة", 0, 199), ("medium", "متوسطة", 200, 300), ("long", "طويلة", 301, 10 ** 6))


def length_bucket(page_count):
    if not page_count:
        return None
    for key, _label, low, high in LENGTH_BUCKETS:
        if low <= page_count <= high:
            return key
    return None


_KEEP = object()
_weekly_cache = {"at": 0.0, "data": None}


class Library:
    @staticmethod
    def add_book(title, desc, pdf_name, cover_name, author=None, genre=None, page_count=None):
        """اضافة كتاب جديد إلى قاعدة البيانات"""
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO books (title, desc_text, pdf_path, cover_path, author, genre, page_count) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (title, desc, pdf_name, cover_name, author, genre, page_count) # title هنا هو الاسم العربي الذي أدخلته في الفورم
        )
        book_id = cur.fetchone()[0]

        conn.commit()
        cur.close()
        conn.close()
        return book_id


    @staticmethod
    def get_book_id(book_id):
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute("SELECT id, title, desc_text, cover_path, pdf_path, download_count, author, genre, page_count FROM books WHERE id=%s", (book_id,))
        book = cur.fetchone() # جلب مسارات الملفات القديمة من قاعدة البيانات

        conn.commit()
        cur.close()
        conn.close()
        return book
    @staticmethod
    def edit_book(title, desc, cover_name, pdf_name, book_id, author=_KEEP, genre=_KEEP, page_count=_KEEP):
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # ai_summary = NULL: الملخص المخزّن مبني على العنوان والوصف، فيُعاد توليده بعد أي تعديل
        cur.execute(
            "UPDATE books SET title=%s, desc_text=%s, cover_path=%s, pdf_path=%s, ai_summary=NULL WHERE id=%s",
            (title, desc, cover_name, pdf_name, book_id)
        )
        # المؤلف/النوع/عدد الصفحات تُحدَّث فقط إن مُرّرت
        for column, value in (("author", author), ("genre", genre), ("page_count", page_count)):
            if value is not _KEEP:
                cur.execute(f"UPDATE books SET {column} = %s WHERE id = %s", (value, book_id))
        conn.commit()
        cur.close()
        conn.close()
        
    @staticmethod
    def delete_book(book_id):
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute("DELETE FROM books WHERE id=%s", (book_id,))
        conn.commit()
        cur.close()
        conn.close()


    @staticmethod
    def get_all_books():
        """جلب جميع الكتب من قاعدة البيانات"""
        """عرض الكتب في لوحة التحكم"""
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM books ORDER BY id DESC;")
        books = cur.fetchall()
        cur.close()
        conn.close()
        return books

    @staticmethod
    def get_next_for_bot(last_announced_book_id):
        """أقدم رواية أحدث من آخر رواية أعلنها هذا البوت — تُستخدم بجدولة النشر التلقائي بالقنوات."""
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if last_announced_book_id:
            cur.execute("SELECT * FROM books WHERE id > %s ORDER BY id ASC LIMIT 1", (last_announced_book_id,))
        else:
            cur.execute("SELECT * FROM books ORDER BY id ASC LIMIT 1")
        book = cur.fetchone()
        cur.close()
        conn.close()
        return book

    @staticmethod
    def get_other_books(exclude_id, limit=4):
        """كتب أخرى من نفس المجموعة (عدا الكتاب الحالي) — لقسم 'روايات أخرى' بصفحة الرواية."""
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT * FROM books WHERE id != %s ORDER BY download_count DESC NULLS LAST LIMIT %s",
            (exclude_id, limit)
        )
        books = cur.fetchall()
        cur.close()
        conn.close()
        return books

    @staticmethod
    def get_similar_books(book_id, limit=2):
        """'اقرأ أيضاً': كتب حمّلتها نفس الجلسات التي حمّلت هذا الكتاب (من download.success، بدون الزواحف).
        لو البيانات لا تكفي، يكمل بالأكثر تحميلاً — لا جدول جديد ولا تصنيف يدوي."""
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """
            WITH readers AS (
                SELECT DISTINCT session_id FROM analytics_events
                WHERE event_type = 'download.success' AND metadata->>'book_id' = %s
                  AND session_id IS NOT NULL AND visitor_type NOT IN ('bot', 'crawler', 'scanner')
            ), co AS (
                SELECT e.metadata->>'book_id' AS other_id, COUNT(DISTINCT e.session_id) AS shared
                FROM analytics_events e JOIN readers r ON r.session_id = e.session_id
                WHERE e.event_type = 'download.success' AND e.metadata->>'book_id' <> %s
                GROUP BY 1
            )
            SELECT b.* FROM co JOIN books b ON b.id::text = co.other_id
            ORDER BY co.shared DESC, b.download_count DESC NULLS LAST
            LIMIT %s
            """,
            (str(book_id), str(book_id), limit),
        )
        books = cur.fetchall()
        if len(books) < limit:
            exclude = [book_id] + [b['id'] for b in books]
            cur.execute(
                "SELECT * FROM books WHERE id <> ALL(%s) ORDER BY download_count DESC NULLS LAST LIMIT %s",
                (exclude, limit - len(books)),
            )
            books += cur.fetchall()
        cur.close()
        conn.close()
        return books

    @staticmethod
    def get_weekly_top(limit=5, ttl=600):
        """الأكثر تحميلاً هذا الأسبوع: عدد الجلسات المختلفة التي حمّلت كل كتاب بآخر 7 أيام
        (التحميل المكرر من نفس الجلسة = واحد)، بدون الزواحف والبوتات. كاش 10 دقائق لكل عملية.
        يرجع {book_id: {"rank": n, "downloads": c}}."""
        now = time.time()
        if _weekly_cache["data"] is not None and now - _weekly_cache["at"] < ttl:
            return _weekly_cache["data"]
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT (metadata->>'book_id')::int AS book_id, COUNT(DISTINCT COALESCE(session_id, ip)) AS downloaders
            FROM analytics_events
            WHERE event_type = 'download.success'
              AND occurred_at >= NOW() - INTERVAL '7 days'
              AND visitor_type NOT IN ('bot', 'crawler', 'scanner')
              AND metadata->>'book_id' ~ '^[0-9]+$'
            GROUP BY 1
            ORDER BY downloaders DESC, book_id
            LIMIT %s
            """,
            (limit,),
        )
        data = {book_id: {"rank": i + 1, "downloads": count} for i, (book_id, count) in enumerate(cur.fetchall())}
        cur.close()
        conn.close()
        _weekly_cache.update(at=now, data=data)
        return data

    @staticmethod
    def search(query, limit=None):
        """بحث مُطبَّع (همزات، تاء مربوطة، تشكيل) في العنوان والمؤلف ثم الوصف — المكتبة صغيرة
        فالتطبيع في Python أبسط وأدق من ILIKE. تطابق العنوان/المؤلف يأتي أولاً."""
        from app.utlis.arabic import normalize_ar
        q = normalize_ar(query)
        if not q:
            return []
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT id, title, desc_text, pdf_path, cover_path, download_count, author, genre, page_count FROM books ORDER BY download_count DESC NULLS LAST, id DESC")
        books = cur.fetchall()
        cur.close()
        conn.close()
        primary = [b for b in books if q in normalize_ar(b['title']) or q in normalize_ar(b.get('author'))]
        secondary = [b for b in books if b not in primary and q in normalize_ar(b['desc_text'])]
        results = primary + secondary
        return results[:limit] if limit else results

    @staticmethod
    def get_ai_summary(book_id):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT ai_summary FROM books WHERE id = %s", (book_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row[0] if row else None

    @staticmethod
    def set_ai_summary(book_id, summary):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE books SET ai_summary = %s WHERE id = %s", (summary, book_id))
        conn.commit()
        cur.close()
        conn.close()

    @staticmethod
    def search_books(query):
        """بحث عن كتب بعنوان يحتوي على النص المُعطى"""
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM books WHERE title ILIKE %s ORDER BY id DESC;", (f"%{query}%",))
        books = cur.fetchall()
        cur.close()
        conn.close()
        return books

