import psycopg2
import psycopg2.extras
from db.sadim_db import get_db_connection
from datetime import datetime


class Post:
    def __init__(self, id=None, user_id=None, title=None, content=None,
                 image_path=None, created_at=None, updated_at=None):
        self.id = id
        self.user_id = user_id
        self.title = title
        self.content = content
        self.image_path = image_path
        self.created_at = created_at or datetime.now()
        self.updated_at = updated_at

    def add(self):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO posts (user_id, title, content, image_path)
            VALUES (%s, %s, %s, %s) RETURNING id
        """, (self.user_id, self.title, self.content, self.image_path))
        post_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return post_id

    @staticmethod
    def get_all(limit=10, offset=0):
        """قائمة المنشورات مع اسم الكاتب، للصفحة العامة."""
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT posts.*, users.username, users.profile_image
            FROM posts
            JOIN users ON posts.user_id = users.id
            ORDER BY posts.created_at DESC
            LIMIT %s OFFSET %s
        """, (limit, offset))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows

    @staticmethod
    def get_count():
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM posts")
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        return count

    @staticmethod
    def get_by_id(post_id):
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT posts.*, users.username, users.profile_image
            FROM posts
            JOIN users ON posts.user_id = users.id
            WHERE posts.id = %s
        """, (post_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row

    @staticmethod
    def get_recent(limit=4, exclude_id=None):
        """أحدث المنشورات (عدا منشور معيّن اختيارياً) — لقسم 'منشورات أخرى' بصفحة المنشور والمكتبة."""
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if exclude_id:
            cur.execute("""
                SELECT posts.*, users.username, users.profile_image
                FROM posts JOIN users ON posts.user_id = users.id
                WHERE posts.id != %s
                ORDER BY posts.created_at DESC LIMIT %s
            """, (exclude_id, limit))
        else:
            cur.execute("""
                SELECT posts.*, users.username, users.profile_image
                FROM posts JOIN users ON posts.user_id = users.id
                ORDER BY posts.created_at DESC LIMIT %s
            """, (limit,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows

    @staticmethod
    def get_random(limit=3):
        """منشورات عشوائية لصفحة العرض حتى لا يرى كل مستخدم نفس المحتوى."""
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT posts.*, users.username, users.profile_image
            FROM posts JOIN users ON posts.user_id = users.id
            ORDER BY RANDOM()
            LIMIT %s
        """, (limit,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows

    @staticmethod
    def get_by_user(user_id):
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM posts WHERE user_id = %s ORDER BY created_at DESC", (user_id,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows

    @staticmethod
    def update(post_id, title, content, image_path=None):
        conn = get_db_connection()
        cur = conn.cursor()
        if image_path:
            cur.execute("""
                UPDATE posts SET title = %s, content = %s, image_path = %s, updated_at = NOW()
                WHERE id = %s
            """, (title, content, image_path, post_id))
        else:
            cur.execute("""
                UPDATE posts SET title = %s, content = %s, updated_at = NOW()
                WHERE id = %s
            """, (title, content, post_id))
        conn.commit()
        cur.close()
        conn.close()

    @staticmethod
    def delete_post(post_id, user_id, user_role):
        """حذف منشور (يسمح لصاحب المنشور أو للأدمن فقط)."""
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM posts WHERE id = %s AND (user_id = %s OR %s = 'admin')",
            (post_id, user_id, user_role)
        )
        count = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
        return count > 0
