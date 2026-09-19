
from psycopg2.extras import Json

from app.db.sadim_db import get_db_connection


class AIQuota:
    @staticmethod
    def get_quota(user_id, quota_key):
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT quota_limit, period, is_unlimited FROM ai_quotas WHERE user_id = %s AND quota_key = %s",
                (user_id, quota_key)
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                'limit': row[0],
                'period': row[1],
                'is_unlimited': row[2]
            }
        finally:
            conn.close()

    @staticmethod
    def get_usage(user_id, quota_key, period='daily'):
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            if period == 'daily':
                cur.execute(
                    "SELECT COUNT(*) FROM ai_usage WHERE user_id = %s AND event_type = %s AND created_at::date = CURRENT_DATE",
                    (user_id, quota_key)
                )
            elif period == 'weekly':
                cur.execute(
                    "SELECT COUNT(*) FROM ai_usage WHERE user_id = %s AND event_type = %s AND created_at >= CURRENT_DATE - INTERVAL '7 days'",
                    (user_id, quota_key)
                )
            elif period == 'monthly':
                cur.execute(
                    "SELECT COUNT(*) FROM ai_usage WHERE user_id = %s AND event_type = %s AND created_at >= CURRENT_DATE - INTERVAL '30 days'",
                    (user_id, quota_key)
                )
            else:
                return 0
            return cur.fetchone()[0]
        finally:
            conn.close()

    @staticmethod
    def check_quota(user_id, quota_key):
        quota = AIQuota.get_quota(user_id, quota_key)
        if not quota:
            return True, None
        if quota['is_unlimited']:
            return True, None
        usage = AIQuota.get_usage(user_id, quota_key, quota['period'])
        if usage >= quota['limit']:
            return False, {
                'quota_key': quota_key,
                'limit': quota['limit'],
                'period': quota['period'],
                'usage': usage
            }
        return True, None

    @staticmethod
    def record_usage(user_id, event_type, model='unknown', visitor_id=None, conversation_id=None, metadata=None):
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO ai_usage (user_id, visitor_id, conversation_id, event_type, model, metadata)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    user_id,
                    visitor_id,
                    conversation_id,
                    event_type,
                    model,
                    Json(metadata or {})
                )
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def set_quota(user_id, quota_key, quota_limit, period='daily', is_unlimited=False):
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO ai_quotas (user_id, quota_key, quota_limit, period, is_unlimited)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (user_id, quota_key) DO UPDATE SET
                   quota_limit = EXCLUDED.quota_limit,
                   period = EXCLUDED.period,
                   is_unlimited = EXCLUDED.is_unlimited,
                   updated_at = NOW()""",
                (user_id, quota_key, quota_limit, period, is_unlimited)
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def get_user_quotas(user_id):
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT quota_key, quota_limit, period, is_unlimited FROM ai_quotas WHERE user_id = %s",
                (user_id,)
            )
            return [
                {
                    'quota_key': row[0],
                    'quota_limit': row[1],
                    'period': row[2],
                    'is_unlimited': row[3]
                }
                for row in cur.fetchall()
            ]
        finally:
            conn.close()
