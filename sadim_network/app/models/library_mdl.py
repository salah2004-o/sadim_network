from db.sadim_db import get_db_connection
import psycopg2.extras
from datetime import datetime
import time

class Library:
    @staticmethod
    def add_book(title, desc, pdf_name, cover_name):
        """اضافة كتاب جديد إلى قاعدة البيانات"""
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO books (title, desc_text, pdf_path, cover_path) VALUES (%s, %s, %s, %s)",
            (title, desc, pdf_name, cover_name) # title هنا هو الاسم العربي الذي أدخلته في الفورم   
        )

        conn.commit()
        cur.close()
        conn.close()


    @staticmethod
    def get_book_id(book_id):
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute("SELECT id, title, desc_text, cover_path, pdf_path, download_count  FROM books WHERE id=%s", (book_id,))
        book = cur.fetchone() # جلب مسارات الملفات القديمة من قاعدة البيانات

        conn.commit()
        cur.close()
        conn.close()
        return book
    @staticmethod
    def edit_book(title, desc, cover_name, pdf_name, book_id):
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute(
            "UPDATE books SET title=%s, desc_text=%s, cover_path=%s, pdf_path=%s WHERE id=%s",
            (title, desc, cover_name, pdf_name, book_id)
        )
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

