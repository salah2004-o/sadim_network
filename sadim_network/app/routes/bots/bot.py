import requests
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app.models.bot_model import Bot
from app.models.quote_model import Quote
from app.models.bot_feature_model import BotFeature
from app.models.bot_limit_model import BotLimitGrant
from app.bot.bot_runner import start_bot, stop_bot, get_all_features

bot_bp = Blueprint('bots', __name__, url_prefix='/bots')


def _verify_token(token: str) -> bool:
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{token}/getMe",
            timeout=5
        )
        return r.status_code == 200 and r.json().get("ok")
    except Exception:
        return False


def _is_owner_or_admin(bot_data, user_id) -> bool:
    return bool(bot_data) and (bot_data.user_id == user_id or session.get('role') == 'admin')


@bot_bp.route("/")
def my_bots():
    if 'user_id' not in session:
        return redirect(url_for('loading_bp.login'))

    user_id = session['user_id']
    bots = Bot.get_by_user(user_id)
    limit_status = BotLimitGrant.get_status_for_user(user_id, current_bot_count=len(bots))
    return render_template("bot.html", bots=bots, username=session.get('username', ''), limit_status=limit_status)


@bot_bp.route("/add", methods=["POST"])
def add_bot():
    if 'user_id' not in session:
        return redirect(url_for('loading_bp.login'))

    user_id = session['user_id']
    bot_token = request.form.get("bot_token", "").strip()
    channel = request.form.get("channel", "").strip()

    if not bot_token or not channel:
        flash("يرجى ملء جميع الحقول.", "error")
        return redirect(url_for('bots.my_bots'))

    # تحقق من الحد الفعلي لهذا المستخدم (افتراضي 1، أو حد مخصص من الإدارة، أو غير محدود)
    effective_limit = BotLimitGrant.get_effective_limit(user_id)
    if effective_limit is not None and len(Bot.get_by_user(user_id)) >= effective_limit:
        flash(f"وصلت للحد المسموح به ({effective_limit} بوت). تواصل مع الإدارة لزيادة الحد.", "error")
        return redirect(url_for('bots.my_bots'))

    # تحقق من التوكن مع Telegram
    if not _verify_token(bot_token):
        flash("التوكن غير صحيح أو منتهي الصلاحية.", "error")
        return redirect(url_for('bots.my_bots'))

    # تحقق من التوكن مش مكرر
    if Bot.get_by_token(bot_token):
        flash("هذا التوكن مستخدم بالفعل.", "error")
        return redirect(url_for('bots.my_bots'))

    # حفظ وتشغيل
    new_bot = Bot(user_id=user_id, bot_token=bot_token, channel=channel, is_active=True)
    new_bot_id = new_bot.add()
    Bot.refresh_telegram_info(new_bot_id, bot_token)
    start_bot(new_bot_id, bot_token, channel)

    flash("✅ تم ربط البوت وتفعيله بنجاح!", "success")
    return redirect(url_for('bots.my_bots'))


@bot_bp.route("/delete/<int:bot_id>", methods=["POST"])
def delete_bot(bot_id):
    if 'user_id' not in session:
        return redirect(url_for('loading_bp.login'))

    user_id = session['user_id']
    bot_data = Bot.get_by_id_from_user(bot_id)

    if not _is_owner_or_admin(bot_data, user_id):
        flash("البوت غير موجود.", "error")
        return redirect(url_for('bots.my_bots'))

    referrer = request.referrer
    stop_bot(bot_data.bot_token)
    Bot.delete(bot_id)
    flash("🗑 تم حذف البوت.", "success")
    return redirect(referrer or url_for('bots.my_bots'))


@bot_bp.route("/toggle/<int:bot_id>", methods=["POST"])
def toggle_bot(bot_id):
    """إيقاف/تشغيل البوت بدون حذفه"""
    if 'user_id' not in session:
        return redirect(url_for('loading_bp.login'))

    user_id = session['user_id']
    bot_data = Bot.get_by_id_from_user(bot_id)

    if not _is_owner_or_admin(bot_data, user_id):
        flash("البوت غير موجود.", "error")
        return redirect(url_for('bots.my_bots'))

    new_status = not bot_data.is_active
    Bot.update(bot_id, new_status)

    if new_status:
        start_bot(bot_data.id, bot_data.bot_token, bot_data.channel)
        flash("✅ تم تشغيل البوت.", "success")
    else:
        stop_bot(bot_data.bot_token)
        flash("⏸ تم إيقاف البوت.", "success")

    return redirect(request.referrer or url_for('bots.my_bots'))


@bot_bp.route("/restart/<int:bot_id>", methods=["POST"])
def restart_bot(bot_id):
    """إعادة تشغيل البوت (إيقاف ثم تشغيل) بدون تغيير حالة التفعيل — يفيد لتطبيق تحديثات فوراً"""
    if 'user_id' not in session:
        return redirect(url_for('loading_bp.login'))

    user_id = session['user_id']
    bot_data = Bot.get_by_id_from_user(bot_id)

    if not _is_owner_or_admin(bot_data, user_id):
        flash("البوت غير موجود.", "error")
        return redirect(url_for('bots.my_bots'))

    if bot_data.is_active:
        stop_bot(bot_data.bot_token)
        start_bot(bot_data.id, bot_data.bot_token, bot_data.channel)
        flash("🔄 تم إعادة تشغيل البوت.", "success")
    else:
        flash("البوت موقوف حالياً، شغّله أولاً.", "error")

    return redirect(request.referrer or url_for('bots.my_bots'))


@bot_bp.route("/refresh/<int:bot_id>", methods=["POST"])
def refresh_bot_info(bot_id):
    """تحديث اسم/يوزرنيم البوت من تيليجرام (getMe) — أدمن فقط عملياً بما إنه زر بلوحة الأدمن"""
    if 'user_id' not in session:
        return redirect(url_for('loading_bp.login'))

    user_id = session['user_id']
    bot_data = Bot.get_by_id_from_user(bot_id)

    if not _is_owner_or_admin(bot_data, user_id):
        flash("البوت غير موجود.", "error")
        return redirect(url_for('bots.my_bots'))

    if Bot.refresh_telegram_info(bot_id, bot_data.bot_token):
        flash("✅ تم تحديث بيانات البوت من تيليجرام.", "success")
    else:
        flash("⚠️ تعذر الوصول لتيليجرام حالياً، حاول لاحقاً.", "error")

    return redirect(request.referrer or url_for('bots.my_bots'))


@bot_bp.route("/manage/<int:bot_id>")
def manage_bot(bot_id):
    if 'user_id' not in session:
        return redirect(url_for('loading_bp.login'))

    user_id = session['user_id']
    bot_data = Bot.get_by_id_from_user(bot_id)

    if not _is_owner_or_admin(bot_data, user_id):
        flash("البوت غير موجود.", "error")
        return redirect(url_for('bots.my_bots'))

    quotes = Quote.get_all_by_bot(bot_id)

    if not bot_data.claim_code:
        bot_data.claim_code = Bot.ensure_claim_code(bot_id)

    overrides = BotFeature.get_overrides(bot_id)
    features = [
        {**feat, "enabled": overrides.get(feat["key"], True)}
        for feat in get_all_features()
    ]

    return render_template("manage_bot.html", bot=bot_data, quotes=quotes, features=features)


@bot_bp.route("/<int:bot_id>/feature/toggle", methods=["POST"])
def toggle_feature(bot_id):
    if 'user_id' not in session:
        return redirect(url_for('loading_bp.login'))

    user_id = session['user_id']
    bot_data = Bot.get_by_id_from_user(bot_id)

    if not _is_owner_or_admin(bot_data, user_id):
        flash("البوت غير موجود.", "error")
        return redirect(url_for('bots.my_bots'))

    feature_key = request.form.get("feature_key", "").strip()
    valid_keys = {f["key"] for f in get_all_features()}
    if feature_key not in valid_keys:
        flash("ميزة غير معروفة.", "error")
        return redirect(url_for('bots.manage_bot', bot_id=bot_id))

    currently_enabled = BotFeature.is_enabled(bot_id, feature_key)
    BotFeature.set_enabled(bot_id, feature_key, not currently_enabled)

    # نعيد تشغيل البوت فوراً حتى يطبّق التغيير مباشرة (الميزات المفعّلة تُقرأ مرة وحدة وقت تشغيل البوت)
    if bot_data.is_active:
        stop_bot(bot_data.bot_token)
        start_bot(bot_data.id, bot_data.bot_token, bot_data.channel)

    flash("✅ تم تحديث الميزة.", "success")
    return redirect(url_for('bots.manage_bot', bot_id=bot_id))


@bot_bp.route("/<int:bot_id>/unlink-owner", methods=["POST"])
def unlink_owner(bot_id):
    """يفك ربط حساب تيليجرام صاحب البوت الحالي ويولّد كود مطالبة جديد — الطريقة الوحيدة
    الآمنة لتغيير المالك (بدل ما يقدر أي شخص يعرف الكود القديم يسحب الملكية عبر /claim)."""
    if 'user_id' not in session:
        return redirect(url_for('loading_bp.login'))

    user_id = session['user_id']
    bot_data = Bot.get_by_id_from_user(bot_id)

    if not _is_owner_or_admin(bot_data, user_id):
        flash("البوت غير موجود.", "error")
        return redirect(url_for('bots.my_bots'))

    Bot.unlink_owner(bot_id)
    flash("✅ تم فك ربط حساب المالك وتوليد كود مطالبة جديد. استخدم /claim بالكود الجديد لإعادة الربط.", "success")
    return redirect(url_for('bots.manage_bot', bot_id=bot_id))


@bot_bp.route("/<int:bot_id>/quote/add", methods=["POST"])
def add_quote(bot_id):
    if 'user_id' not in session:
        return redirect(url_for('loading_bp.login'))

    user_id = session['user_id']
    bot_data = Bot.get_by_id_from_user(bot_id)

    if not _is_owner_or_admin(bot_data, user_id):
        flash("البوت غير موجود.", "error")
        return redirect(url_for('bots.my_bots'))

    text = request.form.get("text", "").strip()
    author = request.form.get("author", "").strip()

    if not text:
        flash("يرجى كتابة نص الاقتباس.", "error")
        return redirect(url_for('bots.manage_bot', bot_id=bot_id))

    Quote(bot_id=bot_id, text=text, author=author or None).add_to_db()
    flash("✅ تمت إضافة الاقتباس.", "success")
    return redirect(url_for('bots.manage_bot', bot_id=bot_id))
