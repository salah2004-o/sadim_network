"""تعبئة المؤلف والنوع وعدد الصفحات للكتب الموجودة (مرة واحدة بعد ترحيل sadim_db.py).

التشغيل من مجلد sadim_network/:
    BOT_WORKER=false python app/db/backfill_book_meta.py

- المؤلف والنوع: القيم الافتراضية فقط للكتب التي لا قيمة لها (لا يكتب فوق ما أُدخل يدوياً).
  عدّل الاستثناءات (مثل المجموعات القصصية) من لوحة الإدارة بعدها.
- عدد الصفحات: يُحسب من ملف PDF لكل كتاب بلا page_count.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("BOT_WORKER", "false")

from app.db.sadim_db import get_db_connection
from app.models.library_mdl import DEFAULT_AUTHOR, DEFAULT_GENRE
from app.routes.shared import UPLOAD_FOLDER
from app.utlis.media import pdf_page_count


def main():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE books SET author = %s WHERE author IS NULL OR author = ''", (DEFAULT_AUTHOR,))
    print(f"author: {cur.rowcount} كتاب")
    cur.execute("UPDATE books SET genre = %s WHERE genre IS NULL OR genre = ''", (DEFAULT_GENRE,))
    print(f"genre: {cur.rowcount} كتاب")
    cur.execute("SELECT id, title, pdf_path FROM books WHERE page_count IS NULL")
    for book_id, title, pdf_path in cur.fetchall():
        pages = pdf_page_count(os.path.join(UPLOAD_FOLDER, pdf_path or ""))
        if pages:
            cur.execute("UPDATE books SET page_count = %s WHERE id = %s", (pages, book_id))
        print(f"#{book_id} {title}: {pages or 'تعذّر الحساب'}")
    conn.commit()
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
