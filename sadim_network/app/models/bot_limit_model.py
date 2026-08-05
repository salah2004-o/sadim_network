#sadim_network/app/models/bot_limit_model.py
# نظام حد عدد البوتات لكل مستخدم — حد افتراضي (1) لكل الجميع، إلا لو فيه صف استثناء
# صريح بجدول bot_limit_grants (نفس فكرة bot_features: تفعيل افتراضي إلا لو فيه تسجيل مخالف).
# upsert() هي نقطة الدخول الوحيدة لمنح/تعديل/تمديد الحد — أي نظام دفع مستقبلي يناديها
# بعد نجاح الدفع بدون أي حاجة لإعادة بناء هالمنطق.
from datetime import datetime, timedelta
from db.sadim_db import get_db_connection

DEFAULT_LIMIT = 1
EXPIRING_SOON_DAYS = 7


def _row_to_dict(row):
    if not row:
        return None
    return {
        "id": row[0], "user_id": row[1], "bot_limit": row[2], "is_unlimited": row[3],
        "starts_at": row[4], "expires_at": row[5],
        "reminder_7d_sent": row[6], "reminder_expiry_sent": row[7],
        "created_at": row[8], "updated_at": row[9],
    }


class BotLimitGrant:

    @staticmethod
    def get_for_user(user_id):
        """يرجّع الصف الخام (dict) لو فيه استثناء مسجَّل لهذا المستخدم، وإلا None."""
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM bot_limit_grants WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return _row_to_dict(row)

    @staticmethod
    def _is_active(grant):
        """صف موجود وما انتهت صلاحيته (أو بلا تاريخ انتهاء أصلاً)."""
        if not grant:
            return False
        if grant["expires_at"] is None:
            return True
        return grant["expires_at"] > datetime.now()

    @staticmethod
    def get_effective_limit(user_id):
        """الحد الفعلي الحالي — None يعني غير محدود، رقم يعني الحد الأقصى.
        صف منتهي الصلاحية يُعامَل كأنه غير موجود (رجوع تلقائي للحد الافتراضي)."""
        grant = BotLimitGrant.get_for_user(user_id)
        if not BotLimitGrant._is_active(grant):
            return DEFAULT_LIMIT
        return None if grant["is_unlimited"] else grant["bot_limit"]

    @staticmethod
    def get_status_for_user(user_id, current_bot_count=None):
        """معلومات كاملة جاهزة للعرض (صفحة الحساب / لوحة الأدمن)."""
        grant = BotLimitGrant.get_for_user(user_id)
        active = BotLimitGrant._is_active(grant)

        if not grant:
            status = "default"
        elif not active:
            status = "expired"
        elif grant["expires_at"] and grant["expires_at"] <= datetime.now() + timedelta(days=EXPIRING_SOON_DAYS):
            status = "expiring_soon"
        else:
            status = "active"

        if not active:
            effective_limit = DEFAULT_LIMIT
        elif grant["is_unlimited"]:
            effective_limit = None
        else:
            effective_limit = grant["bot_limit"]
        expires_at = grant["expires_at"] if (grant and active) else None
        days_left = (expires_at - datetime.now()).days if expires_at else None

        return {
            "status": status,
            "effective_limit": effective_limit,
            "is_unlimited": bool(grant and active and grant["is_unlimited"]),
            "expires_at": expires_at,
            "days_left": days_left,
            "current_bot_count": current_bot_count,
        }

    @staticmethod
    def upsert(user_id, bot_limit=None, is_unlimited=False, expires_at=None, starts_at=None):
        """يمنح/يعدّل/يمدّد حد مستخدم. يصفّر أعلام التذكير حتى ترسل تذكيرات صحيحة للمدة الجديدة."""
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO bot_limit_grants (user_id, bot_limit, is_unlimited, starts_at, expires_at,
                                           reminder_7d_sent, reminder_expiry_sent, updated_at)
            VALUES (%s, %s, %s, COALESCE(%s, NOW()), %s, FALSE, FALSE, NOW())
            ON CONFLICT (user_id) DO UPDATE SET
                bot_limit = EXCLUDED.bot_limit,
                is_unlimited = EXCLUDED.is_unlimited,
                starts_at = EXCLUDED.starts_at,
                expires_at = EXCLUDED.expires_at,
                reminder_7d_sent = FALSE,
                reminder_expiry_sent = FALSE,
                updated_at = NOW()
        """, (user_id, bot_limit, is_unlimited, starts_at, expires_at))
        conn.commit()
        cur.close()
        conn.close()

    @staticmethod
    def cancel(user_id):
        """إلغاء الاستثناء ورجوع فوري للحد الافتراضي."""
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM bot_limit_grants WHERE user_id = %s", (user_id,))
        conn.commit()
        cur.close()
        conn.close()

    @staticmethod
    def get_all_with_stats():
        """لصفحة الأدمن: كل مستخدم عنده استثناء مسجَّل + اسمه + عدد بوتاته الحالي."""
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT g.user_id, u.username, u.email,
                   g.bot_limit, g.is_unlimited, g.starts_at, g.expires_at,
                   (SELECT COUNT(*) FROM bots b WHERE b.user_id = g.user_id) AS bot_count
            FROM bot_limit_grants g
            JOIN users u ON u.id = g.user_id
            ORDER BY g.updated_at DESC
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        results = []
        for r in rows:
            user_id, username, email, bot_limit, is_unlimited, starts_at, expires_at, bot_count = r
            active = expires_at is None or expires_at > datetime.now()
            if not active:
                status = "expired"
            elif expires_at and expires_at <= datetime.now() + timedelta(days=EXPIRING_SOON_DAYS):
                status = "expiring_soon"
            else:
                status = "active"
            results.append({
                "user_id": user_id, "username": username, "email": email,
                "bot_limit": bot_limit, "is_unlimited": is_unlimited,
                "starts_at": starts_at, "expires_at": expires_at,
                "days_left": (expires_at - datetime.now()).days if expires_at else None,
                "bot_count": bot_count, "status": status,
            })
        return results

    @staticmethod
    def get_expiring_within_days(days):
        """استثناءات نشطة تنتهي خلال N يوم القادمة، وما أُرسل لها تذكير بعد."""
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT g.user_id, u.email, u.username, g.expires_at
            FROM bot_limit_grants g JOIN users u ON u.id = g.user_id
            WHERE g.expires_at IS NOT NULL
              AND g.expires_at > NOW()
              AND g.expires_at <= NOW() + (%s || ' days')::interval
              AND g.reminder_7d_sent = FALSE
        """, (days,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [{"user_id": r[0], "email": r[1], "username": r[2], "expires_at": r[3]} for r in rows]

    @staticmethod
    def get_freshly_expired():
        """استثناءات انتهت للتو، وما أُرسل لها تذكير انتهاء بعد."""
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT g.user_id, u.email, u.username, g.expires_at
            FROM bot_limit_grants g JOIN users u ON u.id = g.user_id
            WHERE g.expires_at IS NOT NULL
              AND g.expires_at <= NOW()
              AND g.reminder_expiry_sent = FALSE
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [{"user_id": r[0], "email": r[1], "username": r[2], "expires_at": r[3]} for r in rows]

    @staticmethod
    def mark_reminder_sent(user_id, which):
        """which: '7d' أو 'expiry'."""
        column = "reminder_7d_sent" if which == "7d" else "reminder_expiry_sent"
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(f"UPDATE bot_limit_grants SET {column} = TRUE WHERE user_id = %s", (user_id,))
        conn.commit()
        cur.close()
        conn.close()
