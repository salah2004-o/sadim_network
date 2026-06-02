from db import sadim_db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime


class User:
    def __init__(
        self,
        id=None,
        username=None,
        user_agent=None,
        ip=None,
        name=None,
        email=None,
        password=None,
        password_hash=None,
        role='user',
        is_verified=False,
        profile_image=None,
        last_login=None,
        status='active',
        created_at=None,
        updated_at=None
    ):
        self.id = id
        self.username = username
        self.user_agent = user_agent
        self.ip = ip
        self.name = name
        self.email = email
        self.password_hash = (
            generate_password_hash(password) if password else password_hash
        )
        self.role = role
        self.is_verified = is_verified
        self.profile_image = profile_image
        self.last_login = last_login
        self.status = status
        self.created_at = created_at
        self.updated_at = updated_at

    # ---------- CREATE ----------
    def add_to_db(self):
        conn = sadim_db.get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (
                username, user_agent, ip, name, email,
                password_hash, role, profile_image,
                last_login, status, is_verified,
                created_at, updated_at
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id;
        """, (
            self.username,
            self.user_agent,
            self.ip,
            self.name,
            self.email,
            self.password_hash,
            self.role,
            self.profile_image,
            self.last_login,
            self.status,
            self.is_verified,
            datetime.now(),
            datetime.now()
        ))
        user_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return user_id

    # ---------- GET BY ID ----------
    @staticmethod
    def get_by_id(user_id):
        conn = sadim_db.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE id=%s;", (user_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return User._row_to_user(row)

    # ---------- GET BY EMAIL ----------
    @staticmethod
    def get_by_email(email):
        conn = sadim_db.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email=%s;", (email,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return User._row_to_user(row)

    # ---------- GET BY USERNAME ----------
    @staticmethod
    def get_by_username(username):
        conn = sadim_db.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username=%s;", (username,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return User._row_to_user(row)

    # ---------- GET ALL ----------
    @staticmethod
    def get_all():
        conn = sadim_db.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users;")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [User._row_to_user(row) for row in rows]

    # ---------- DELETE ----------
    @staticmethod
    def delete(user_id):
        conn = sadim_db.get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE id=%s;", (user_id,))
        conn.commit()
        cur.close()
        conn.close()
        return True

    # ---------- VERIFY EMAIL ----------
    @staticmethod
    def verify_email(user_id):
        conn = sadim_db.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET is_verified=TRUE, updated_at=%s WHERE id=%s;",
            (datetime.now(), user_id)
        )
        conn.commit()
        cur.close()
        conn.close()
        return True

    # ---------- AUTH ----------
    @staticmethod
    def authenticate(email, password, role=None):
        user = User.get_by_email(email)
        if not user:
            return None
        if not check_password_hash(user.password_hash, password):
            return None
        if role and user.role != role:
            return None
        return user

    @staticmethod
    def authenticate_admin(email, password):
        return User.authenticate(email, password, role='admin')

    def update_user(self):
     """تحديث بيانات المستخدم في قاعدة البيانات"""
     conn = sadim_db.get_db_connection()
     cur = conn.cursor()

     try:
        # تحقق من تكرار الإيميل
        cur.execute(
            "SELECT id FROM users WHERE email=%s AND id!=%s",
            (self.email, self.id)
        )
        if cur.fetchone():
            return {"error": "email_exists"}

        cur.execute("""
            UPDATE users
            SET name=%s,
                username=%s,
                user_agent=%s,
                ip=%s,
                email=%s,
                password_hash=%s,
                role=%s,
                profile_image=%s,
                last_login=%s,
                is_verified=%s,
                updated_at=%s
            WHERE id=%s;
        """, (
            self.name,
            self.username,
            self.user_agent,
            self.ip,
            self.email,
            self.password_hash,
            self.role,
            self.profile_image,
            self.last_login,
            self.is_verified,
            datetime.now(),
            self.id
        ))

        conn.commit()
        return {"ok": True}

     except Exception as e:
        conn.rollback()
        return {"error": "db_error"}

     finally:
        cur.close()
        conn.close()

    # ---------- INTERNAL MAPPER ----------
    @staticmethod
    def _row_to_user(row): # هذه الدالة يظهر أن هناك مشكلة في تنسيق التاريخ في قاعدة البيانات، لذلك تم تعديلها للتأكد من تحويل النص إلى كائن datetime بشكل صحيح.
        if not row:
            return None
    
        last_login = row[9]
        if last_login and isinstance(last_login, str):
            last_login = datetime.strptime(last_login, "%Y-%m-%d %H:%M:%S.%f")
    
        return User(
            id=row[0],
            username=row[1],
            user_agent=row[2],
            ip=row[3],
            name=row[4],
            email=row[5],
            password_hash=row[6],
            role=row[7],
            profile_image=row[8],
            last_login=last_login,  # ← استخدم المتغير المحول هنا
            status=row[10],
            is_verified=row[11],
            created_at=row[12],
            updated_at=row[13]
        )
    
    @staticmethod
    def google_authenticate(google_id, email, name, picture):
       conn = sadim_db.get_db_connection()
       cur = conn.cursor()
        # هل المستخدم موجود؟
       cur.execute("SELECT id, role, username FROM users WHERE google_id = %s OR email = %s", (google_id, email))
       existing = cur.fetchone()

       if existing:
            user_id, role, username = existing
            # تحديث google_id لو سجل قبل بإيميل
            cur.execute("UPDATE users SET google_id = %s WHERE id = %s", (google_id, user_id))
       else:
            # مستخدم جديد
            username = email.split('@')[0]
            cur.execute("""
                INSERT INTO users (username, name, email, google_id, is_verified, profile_image, password_hash)
                VALUES (%s, %s, %s, %s, TRUE, %s, NULL)
                RETURNING id, role
            """, (username, name, email, google_id, picture))
            user_id, role = cur.fetchone()