from flask import Blueprint, render_template, request, redirect, url_for, session
from app.models.bot_model import Bot
from app.models.quote_model import Quote
from app.models.user import User

bot_bp = Blueprint('bot', __name__, url_prefix='/bots')


@bot_bp.route("/bot")
def bot():
    user_id = session.get('user_id')
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    return render_template("bot.html")