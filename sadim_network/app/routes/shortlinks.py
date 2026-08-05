# روابط مختصرة — /s/<code> يعيد التوجيه للرابط الأصلي
from flask import Blueprint, redirect, abort
from app.models.short_link_model import ShortLink

shortlinks_bp = Blueprint('shortlinks', __name__)


@shortlinks_bp.route('/s/<code>')
def go(code):
    link = ShortLink.get_by_code(code)
    if not link:
        abort(404)
    ShortLink.increment_clicks(link.id)
    return redirect(link.original_url)
