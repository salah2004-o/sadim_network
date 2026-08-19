from flask import Blueprint, render_template
main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    from app.models.post_model import Post
    from app.models.bot_model import Bot
    from app.models.analytics_dashboard import get_top_book_this_week
    recent_posts = Post.get_recent(limit=3)
    active_bot_count = len(Bot.get_active_bots())
    top_book_week = get_top_book_this_week()
    return render_template(
        'index.html',
        recent_posts=recent_posts,
        active_bot_count=active_bot_count,
        top_book_week=top_book_week,
    )


@main_bp.route('/about')
def about():
    return render_template('about.html')


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

