# FILE: app/__init__.py
# sadim_network/app/__init__.py
from flask import Flask, render_template
from werkzeug.middleware.proxy_fix import ProxyFix
from app import config
from app.limiter import limiter
from authlib.integrations.flask_client import OAuth
app = Flask(__name__)
app.config.from_object('app.config.settings')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 ميجا
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
limiter.init_app(app)


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


@app.context_processor
def inject_nav_user():
    """يوفر بيانات المستخدم الحالي (وأهمها صورة البروفايل) لكل القوالب تلقائياً —
    خصوصاً شل التنقل الموحّد (layouts/public.html) اللي يُستخدم بكل صفحة عامة،
    بدون ما يحتاج كل route يتذكر يمرر user بنفسه."""
    from flask import session
    if 'user_id' not in session:
        return {}
    from app.models.user import User
    return {'nav_user': User.get_by_id(session['user_id'])}


@app.context_processor
def inject_ai_page_context():
    """Detect article/book detail pages so the FAB can open a context side panel."""
    from flask import request
    import re
    path = request.path or ''
    article = re.search(r'^/articles/(\d+)/?$', path)
    if article:
        return {'ai_context_type': 'article', 'ai_context_id': article.group(1)}
    book = re.search(r'^/library/(\d+)/?$', path, re.I)
    if book:
        return {'ai_context_type': 'book', 'ai_context_id': book.group(1)}
    return {'ai_context_type': '', 'ai_context_id': ''}

oauth = OAuth(app)
google_oauth = oauth.register(
    name='google',
    client_id=app.config['GOOGLE_CLIENT_ID'],
    client_secret=app.config['GOOGLE_CLIENT_SECRET'],
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'}
    )


from app.routes.index import main_bp
from app.routes.errors import errors_bp 
from app.routes.admin.admin import admin_bp
from app.routes.loding import loading_bp
from app.routes.register import register_bp
from app.routes.LIBRARY_SADIM.library import library_bp
from app.routes.admin.profile import profile_bp
from app.routes.menu_route import menu_bp
from app.routes.bots.bot import bot_bp as bots_bp
from app.routes.articles.articles import articles_bp
from app.routes.shortlinks import shortlinks_bp
from app.routes.ai import ai_bp
from app.routes.personal import personal_bp

#blueprint
app.register_blueprint(loading_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(profile_bp)
app.register_blueprint(menu_bp)
app.register_blueprint(errors_bp)
app.register_blueprint(main_bp)
app.register_blueprint(register_bp)
app.register_blueprint(library_bp)
app.register_blueprint(bots_bp)
app.register_blueprint(articles_bp)
app.register_blueprint(shortlinks_bp)
app.register_blueprint(ai_bp)
app.register_blueprint(personal_bp)

from app.bot.bot_runner import restore_all_bots
restore_all_bots()