from db.sadim_db import get_db_connection


class BotActivity:
    @staticmethod
    def record(bot_id, chat_id, is_command):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO bot_activity (bot_id, chat_id, message_count, command_count, last_seen)
            VALUES (%s, %s, 1, %s, NOW())
            ON CONFLICT (bot_id, chat_id) DO UPDATE SET
                message_count = bot_activity.message_count + 1,
                command_count = bot_activity.command_count + EXCLUDED.command_count,
                last_seen = NOW()
        """, (bot_id, chat_id, 1 if is_command else 0))
        conn.commit()
        cur.close()
        conn.close()

    @staticmethod
    def get_stats(bot_id):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*), COALESCE(SUM(message_count), 0), COALESCE(SUM(command_count), 0), MAX(last_seen)
            FROM bot_activity WHERE bot_id = %s
        """, (bot_id,))
        users, messages, commands, last_seen = cur.fetchone()
        cur.close()
        conn.close()
        return {"users": users, "messages": messages, "commands": commands, "last_seen": last_seen}
