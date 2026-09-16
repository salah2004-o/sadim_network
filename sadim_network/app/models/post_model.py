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
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (
            self.user_id,
            self.title,
            self.content,
            self.image_path
        ))

        post_id = cur.fetchone()[0]

        conn.commit()
        cur.close()
        conn.close()

        return post_id

    @staticmethod
    def get_all(limit=10, offset=0, search=None, feed_seed=None):
        """
        جلب المنشورات للصفحة العامة.

        - يدعم البحث في العنوان والمحتوى.
        - إذا تم تمرير feed_seed يتم ترتيب المنشورات
          بطريقة ثابتة لكل زائر بدلاً من RANDOM().
        """

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        conditions = []
        params = []

        # البحث
        if search:
            conditions.append("""
                (
                    posts.title ILIKE %s
                    OR posts.content ILIKE %s
                )
            """)

            search_pattern = f"%{search}%"
            params.extend([search_pattern, search_pattern])

        where_clause = ""

        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        # ترتيب مخصص وثابت لكل زائر
        if feed_seed is not None:
            order_clause = """
                md5(
                    posts.id::text || ':' || %s::text
                )
            """
            params.append(str(feed_seed))
        else:
            order_clause = "posts.created_at DESC"

        query = f"""
            SELECT
                posts.*,
                users.username,
                users.profile_image
            FROM posts
            JOIN users ON posts.user_id = users.id
            {where_clause}
            ORDER BY {order_clause}
            LIMIT %s OFFSET %s
        """

        params.extend([limit, offset])

        cur.execute(query, tuple(params))

        rows = cur.fetchall()

        cur.close()
        conn.close()

        return rows

    @staticmethod
    def get_count(search=None):
        """
        عدد المنشورات.
        يدعم نفس البحث المستخدم في get_all()
        حتى تكون pagination صحيحة.
        """

        conn = get_db_connection()
        cur = conn.cursor()

        if search:
            search_pattern = f"%{search}%"

            cur.execute("""
                SELECT COUNT(*)
                FROM posts
                WHERE
                    title ILIKE %s
                    OR content ILIKE %s
            """, (
                search_pattern,
                search_pattern
            ))
        else:
            cur.execute("""
                SELECT COUNT(*)
                FROM posts
            """)

        count = cur.fetchone()[0]

        cur.close()
        conn.close()

        return count

    @staticmethod
    def get_by_id(post_id):
        conn = get_db_connection()
        cur = conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        )

        cur.execute("""
            SELECT
                posts.*,
                users.username,
                users.profile_image
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
        """
        أحدث المنشورات
        عدا منشور معيّن اختيارياً.
        """

        conn = get_db_connection()
        cur = conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        )

        if exclude_id:
            cur.execute("""
                SELECT
                    posts.*,
                    users.username,
                    users.profile_image
                FROM posts
                JOIN users ON posts.user_id = users.id
                WHERE posts.id != %s
                ORDER BY posts.created_at DESC
                LIMIT %s
            """, (
                exclude_id,
                limit
            ))
        else:
            cur.execute("""
                SELECT
                    posts.*,
                    users.username,
                    users.profile_image
                FROM posts
                JOIN users ON posts.user_id = users.id
                ORDER BY posts.created_at DESC
                LIMIT %s
            """, (limit,))

        rows = cur.fetchall()

        cur.close()
        conn.close()

        return rows

    @staticmethod
    def get_random(limit=3):
        """
        منشورات عشوائية.

        هذه الدالة أبقيناها للتوافق مع أي مكان
        آخر في المشروع ما زال يستخدمها.
        """

        conn = get_db_connection()
        cur = conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        )

        cur.execute("""
            SELECT
                posts.*,
                users.username,
                users.profile_image
            FROM posts
            JOIN users ON posts.user_id = users.id
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
        cur = conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        )

        cur.execute("""
            SELECT *
            FROM posts
            WHERE user_id = %s
            ORDER BY created_at DESC
        """, (user_id,))

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
                UPDATE posts
                SET
                    title = %s,
                    content = %s,
                    image_path = %s,
                    updated_at = NOW()
                WHERE id = %s
            """, (
                title,
                content,
                image_path,
                post_id
            ))
        else:
            cur.execute("""
                UPDATE posts
                SET
                    title = %s,
                    content = %s,
                    updated_at = NOW()
                WHERE id = %s
            """, (
                title,
                content,
                post_id
            ))

        conn.commit()

        cur.close()
        conn.close()

    @staticmethod
    def delete_post(post_id, user_id, user_role):
        """
        حذف منشور.
        يسمح لصاحب المنشور أو للأدمن.
        """

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            DELETE FROM posts
            WHERE
                id = %s
                AND (
                    user_id = %s
                    OR %s = 'admin'
                )
        """, (
            post_id,
            user_id,
            user_role
        ))

        count = cur.rowcount

        conn.commit()

        cur.close()
        conn.close()

        return count > 0

    @staticmethod
    def register_view(
        post_id,
        session_id=None,
        user_id=None,
        ip=None,
        cooldown_minutes=30
    ):
        """
        تسجيل مشاهدة للمنشور.

        نفس الزائر لا يُحتسب له أكثر من مشاهدة
        خلال فترة cooldown_minutes.

        الأولوية في التعرف على الزائر:
        session_id -> user_id -> IP.
        """

        if not session_id and not user_id and not ip:
            return False

        conn = get_db_connection()
        cur = conn.cursor()

        try:
            # نستخدم session_id عندما يكون متوفراً لأنه
            # أدق من IP في تمييز الزوار.
            if session_id:
                cur.execute("""
                    SELECT 1
                    FROM post_views
                    WHERE
                        post_id = %s
                        AND session_id = %s
                        AND created_at >= NOW() - (%s * INTERVAL '1 minute')
                    LIMIT 1
                """, (
                    post_id,
                    session_id,
                    cooldown_minutes
                ))

            elif user_id:
                cur.execute("""
                    SELECT 1
                    FROM post_views
                    WHERE
                        post_id = %s
                        AND user_id = %s
                        AND created_at >= NOW() - (%s * INTERVAL '1 minute')
                    LIMIT 1
                """, (
                    post_id,
                    user_id,
                    cooldown_minutes
                ))

            else:
                cur.execute("""
                    SELECT 1
                    FROM post_views
                    WHERE
                        post_id = %s
                        AND ip_address = %s
                        AND created_at >= NOW() - (%s * INTERVAL '1 minute')
                    LIMIT 1
                """, (
                    post_id,
                    ip,
                    cooldown_minutes
                ))

            already_viewed = cur.fetchone()

            if already_viewed:
                conn.rollback()
                return False

            cur.execute("""
                INSERT INTO post_views (
                    post_id,
                    user_id,
                    session_id,
                    ip_address
                )
                VALUES (%s, %s, %s, %s)
            """, (
                post_id,
                user_id,
                session_id,
                ip
            ))

            cur.execute("""
                UPDATE posts
                SET views = COALESCE(views, 0) + 1
                WHERE id = %s
            """, (post_id,))

            conn.commit()

            return True

        except Exception:
            conn.rollback()
            raise

        finally:
            cur.close()
            conn.close()