# FILE: app/__init__.py
# sadim_network/app/__init__.py
from flask import Flask, render_template
from app import config
from app.limiter import limiter
from authlib.integrations.flask_client import OAuth
app = Flask(__name__)
app.config.from_object('app.config.settings')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 ميجا
limiter.init_app(app)

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

from app.routes.LIBRARY_SADIM.Agatha_Christie import Library_Agatha_bp
from app.routes.admin.profile import profile_bp
from app.routes.menu_route import menu_bp
#blueprint
app.register_blueprint(loading_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(profile_bp)
app.register_blueprint(menu_bp)
app.register_blueprint(errors_bp)
app.register_blueprint(main_bp)
app.register_blueprint(register_bp)

app.register_blueprint(Library_Agatha_bp)
