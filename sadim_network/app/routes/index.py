from flask import Blueprint, render_template, session, g, url_for
from app.models.home_feed import get_resume_items, get_signal_summary, get_user_state

main_bp = Blueprint('main', __name__)


def _resume_url(item):
    """يبني رابط الاستئناف حسب نوع المحتوى — يستخدم endpoints الموجودة فعلاً
    (لا روتات جديدة)، متطابقاً مع أسماء المسارات الحقيقية في app/routes."""
    if item['content_type'] == 'book':
        return url_for('library.view_book', book_id=item['content_id'])
    return url_for('articles.view_article', post_id=item['content_id'])


@main_bp.route('/')
def index():
    user_id = session.get('user_id')
    resume_items = []
    signals = None
    if user_id:
        resume_items = get_resume_items(user_id, limit=3)
        for item in resume_items:
            item['url'] = _resume_url(item)
        signals = get_signal_summary(user_id)
    user_state = get_user_state(user_id, session_id=g.get('sd_session_id'))
    return render_template(
        'home.html',
        resume_items=resume_items,
        signals=signals,
        user_state=user_state,
        is_authenticated=bool(user_id),
    )


@main_bp.route('/about')
def about():
    return render_template('about.html')


@main_bp.route('/discover')
def discover():
    """بوابة اكتشاف تجمع منتجات ومحتوى سديم قبل الدخول إلى قسم محدد."""
    return render_template('discover.html')


# مسار عام واضح للخدمات (بدل /dashboard/services المضلِّل — يوحي بمسار إداري
# رغم إنه صفحة عامة). المسار القديم يبقى شغّالاً كما هو لأي رابط خارجي محفوظ مسبقاً؛
# هذا فقط المسار الجديد اللي تولّده كل الروابط الداخلية من الآن.
@main_bp.route('/services')
def services():
    from app.routes.admin.services import show_services
    return show_services()


@main_bp.route('/services/<string:type>/<int:item_id>')
def service_detail(type, item_id):
    from app.routes.admin.services import service_detail as _service_detail
    return _service_detail(type, item_id)



@main_bp.route('/Support')

def support():
    return render_template('Support.html')

