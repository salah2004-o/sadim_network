from flask import Blueprint, render_template

menu_bp = Blueprint('menu', __name__)

@menu_bp.route('/menu')
@menu_bp.route('/menu/')
def menu():
    """
    صفحة منيو مطعم شواية ومقلي
    Route: /menu
    Template: templates/menu.html
    """
    return render_template('menu.html')
