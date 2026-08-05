# إدارة بوتات المستخدمين من لوحة تحكم الأدمن
from flask import render_template
from app.routes.admin.admin import admin_bp
from utlis.login_required import login_required
from utlis.permissions import admin_required
from app.models.bot_model import Bot
from app.models.bot_activity_model import BotActivity
from app.models.bot_feature_model import BotFeature
from app.bot.bot_runner import get_all_features


@admin_bp.route('/bots')
@login_required
@admin_required
def manage_bots():
    bots = Bot.get_all_with_owner()
    all_feature_keys = {f["key"] for f in get_all_features()}
    total_features = len(all_feature_keys)

    for b in bots:
        b["stats"] = BotActivity.get_stats(b["id"])
        overrides = BotFeature.get_overrides(b["id"])
        enabled_count = sum(1 for k in all_feature_keys if overrides.get(k, True))
        b["enabled_features_count"] = enabled_count
        b["total_features_count"] = total_features

    return render_template('dashboard/bots_dashboard.html', bots=bots)
