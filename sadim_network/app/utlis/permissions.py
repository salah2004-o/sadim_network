from functools import wraps
from flask import session, redirect, url_for, abort

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('loading_bp.login'))

        if session.get("role") != "admin":
            abort(403)

        return f(*args, **kwargs)
    return decorated_function
