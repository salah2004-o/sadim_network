from db.sadim_db import get_db_connection


class BotFeature:
    """تفعيل/تعطيل ميزات البوت لكل بوت على حدة.
    الافتراضي: أي ميزة مفعّلة إلا لو فيه صف صريح enabled=FALSE — يعني ميزة جديدة تُضاف للنظام
    تكون مفعّلة تلقائياً لكل البوتات القديمة بدون أي migration إضافي."""

    @staticmethod
    def get_overrides(bot_id):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT feature_key, enabled FROM bot_features WHERE bot_id = %s", (bot_id,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return {key: enabled for key, enabled in rows}

    @staticmethod
    def is_enabled(bot_id, feature_key, overrides=None):
        if overrides is None:
            overrides = BotFeature.get_overrides(bot_id)
        return overrides.get(feature_key, True)

    @staticmethod
    def set_enabled(bot_id, feature_key, enabled):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO bot_features (bot_id, feature_key, enabled, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (bot_id, feature_key)
            DO UPDATE SET enabled = EXCLUDED.enabled, updated_at = NOW()
        """, (bot_id, feature_key, enabled))
        conn.commit()
        cur.close()
        conn.close()
