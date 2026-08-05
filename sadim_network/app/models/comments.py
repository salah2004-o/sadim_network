import psycopg2
from db.sadim_db import get_db_connection

class Comments:
    """
    مودل للتحكم في جدول التعليقات (Comments).
    يتعامل مع إضافة، جلب، وحذف التعليقات.
    """

    @staticmethod
    def add_comment(user_id, content, post_id=None, book_id=None):
        """
        إضافة تعليق جديد.
        تم جعل post_id و book_id اختيارية لتتمكن من التعليق على أحدهما أو كليهما.
        """
        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            
            query = """
                INSERT INTO comments (user_id, post_id, book_id, content) 
                VALUES (%s, %s, %s, %s)
                RETURNING id;
            """
            cur.execute(query, (user_id, post_id, book_id, content))
            
            comment_id = cur.fetchone()[0]
            conn.commit()
            cur.close()
            return {"status": "success", "comment_id": comment_id}
            
        except Exception as e:
            if conn:
                conn.rollback()
            return {"status": "error", "message": str(e)}
        finally:
            if conn:
                conn.close()

    @staticmethod
    def get_comments_by_post(post_id):
        """جلب جميع التعليقات الخاصة بمنشور معين، مع اسم صاحب كل تعليق"""
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT c.*, u.username, u.profile_image
            FROM comments c
            JOIN users u ON c.user_id = u.id
            WHERE c.post_id = %s
            ORDER BY c.created_at DESC
        """, (post_id,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows

    @staticmethod
    def get_comments_by_book(book_id):
        """جلب التعليقات مع أسماء أصحابها"""
        conn = get_db_connection()
        # نستخدم RealDictCursor لتسهيل التعامل مع البيانات في القالب
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        query = """
            SELECT c.*, u.username, u.profile_image
            FROM comments c
            JOIN users u ON c.user_id = u.id
            WHERE c.book_id = %s
            ORDER BY c.created_at DESC
        """
        cur.execute(query, (book_id,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows

    @staticmethod
    def delete_comment(comment_id, user_id, user_role):
            """حذف تعليق (يسمح لصاحب التعليق أو للأدمن)"""
            conn = get_db_connection()
            cur = conn.cursor()
            
            # أضفنا علامات تنصيص حول كلمة 'admin' لتصبح قيمة نصية
            query = "DELETE FROM comments WHERE id = %s AND (user_id = %s OR %s = 'admin')"
            
            cur.execute(query, (comment_id, user_id, user_role))
            
            count = cur.rowcount # عدد الصفوف المتأثرة (يجب أن يكون 1 إذا تم الحذف، 0 إذا لم يتم الحذف)
            conn.commit()
            cur.close()
            conn.close()
            return count > 0
    @staticmethod
    def get_all_comments():
        """جلب جميع التعليقات (لأغراض الإدارة مثلاً)"""
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        query = """
            SELECT c.*, u.username, u.profile_image
            FROM comments c
            JOIN users u ON c.user_id = u.id
            ORDER BY c.created_at DESC
        """
        cur.execute(query)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows