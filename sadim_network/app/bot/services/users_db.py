import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_DB_PATH = _DATA_DIR / "users.json"
_LOCK = threading.Lock()


def _ensure_data_dir():
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load():
    _ensure_data_dir()
    if not _DB_PATH.exists():
        return {"users": {}}
    try:
        with open(_DB_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict) or "users" not in data:
                return {"users": {}}
            return data
    except (json.JSONDecodeError, IOError):
        return {"users": {}}


def _save(data):
    _ensure_data_dir()
    tmp_path = str(_DB_PATH) + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, _DB_PATH)


def add_or_update_user(user):
    """Add new user or update existing — called on every interaction with the bot."""
    with _LOCK:
        data = _load()
        user_id = str(user.id)
        now = datetime.now(timezone.utc).astimezone().isoformat()
        entry = data["users"].get(user_id)
        if entry is None:
            entry = {
                "id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "is_active": True,
                "joined_at": now,
                "last_seen": now,
            }
            data["users"][user_id] = entry
        else:
            entry["username"] = user.username
            entry["first_name"] = user.first_name
            entry["is_active"] = True
            entry["last_seen"] = now
        _save(data)


def touch_user(user_id):
    """Update last_seen timestamp for an active user (lightweight presence ping)."""
    with _LOCK:
        data = _load()
        uid = str(user_id)
        if uid in data["users"]:
            data["users"][uid]["last_seen"] = datetime.now(timezone.utc).astimezone().isoformat()
            _save(data)


def get_user(user_id):
    with _LOCK:
        data = _load()
        return data["users"].get(str(user_id))


def get_all_users():
    with _LOCK:
        data = _load()
        return list(data["users"].values())


def get_active_users():
    with _LOCK:
        data = _load()
        return [u for u in data["users"].values() if u.get("is_active")]


def update_user(user_id, **kwargs):
    with _LOCK:
        data = _load()
        uid = str(user_id)
        if uid in data["users"]:
            data["users"][uid].update(kwargs)
            _save(data)


def deactivate_user(user_id):
    with _LOCK:
        data = _load()
        uid = str(user_id)
        if uid in data["users"]:
            data["users"][uid]["is_active"] = False
            _save(data)


def reactivate_user(user_id):
    with _LOCK:
        data = _load()
        uid = str(user_id)
        if uid in data["users"]:
            data["users"][uid]["is_active"] = True
            _save(data)


def get_users_count():
    """Return (total, active) tuple."""
    with _LOCK:
        data = _load()
        total = len(data["users"])
        active = sum(1 for u in data["users"].values() if u.get("is_active"))
        return total, active


def migrate_from_postgres():
    """One-time migration from the users_bot PostgreSQL table to JSON.

    Preserves every existing user without duplicates. Idempotent — safe to call
    multiple times; existing JSON entries are never overwritten.
    Returns the number of newly migrated users.
    """
    from app.db.sadim_db import get_db_connection

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, username, first_name, is_active FROM users_bot ORDER BY id")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    migrated = 0
    with _LOCK:
        data = _load()
        for row in rows:
            user_id = str(row[0])
            if user_id not in data["users"]:
                data["users"][user_id] = {
                    "id": row[0],
                    "username": row[1],
                    "first_name": row[2],
                    "is_active": row[3] if row[3] is not None else True,
                    "joined_at": None,
                    "last_seen": None,
                }
                migrated += 1
        if migrated:
            _save(data)
    return migrated
