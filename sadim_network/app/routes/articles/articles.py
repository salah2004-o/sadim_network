import os
import time
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
from PIL import Image
from app.routes.shared import UPLOAD_FOLDER, allowed_file
from app.limiter import limiter
from app.models.post_model import Post
from app.models.comments import Comments
from app.models.user import User

articles_bp = Blueprint('articles', __name__, url_prefix='/articles')

MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 ميجا
POSTS_PER_PAGE = 10


def _save_article_image(file_storage):
    """يتحقق من الصورة فعلياً (مو بس الامتداد)، يعيد ترميزها بـ Pillow، ويحفظها باسم فريد.
    يرجع (relative_path, error) — إذا نجح: (relative_path, None)، إذا فشل: (None, رسالة الخطأ)."""
    if not file_storage or file_storage.filename == "":
        return None, None  # لا صورة، هذا مسموح (اختياري)

    if not allowed_file(file_storage.filename):
        return None, "امتداد الملف غير مسموح."

    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size > MAX_IMAGE_SIZE:
        return None, "حجم الصورة أكبر من الحد المسموح (٥ ميجا)."

    try:
        img = Image.open(file_storage.stream)
        img.verify()  # يتأكد إنه ملف صورة حقيقي، مو ملف بامتداد مزيف
    except Exception:
        return None, "الملف المرفوع ليس صورة صالحة."

    # لازم نفتحه من جديد لأن verify() يستهلك الملف
    file_storage.stream.seek(0)
    img = Image.open(file_storage.stream)
    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")

    filename = secure_filename(f"post_{int(time.time() * 1000)}.jpg")
    full_path = os.path.join(UPLOAD_FOLDER, filename)
    img.save(full_path, "JPEG", quality=85)  # إعادة ترميز تشيل أي بيانات EXIF/محتوى مخفي

    return f"uploads/{filename}", None


@articles_bp.route("/")
def list_articles():
    page = max(int(request.args.get('page', 1)), 1)
    offset = (page - 1) * POSTS_PER_PAGE
    posts = Post.get_all(limit=POSTS_PER_PAGE, offset=offset)
    total = Post.get_count()
    has_next = offset + POSTS_PER_PAGE < total
    has_prev = page > 1
    return render_template(
        "articles/list.html",
        posts=posts, page=page, has_next=has_next, has_prev=has_prev
    )


@articles_bp.route("/author/<int:user_id>")
def author_profile(user_id):
    author = User.get_by_id(user_id)
    if not author:
        flash("الكاتب غير موجود.", "error")
        return redirect(url_for('articles.list_articles'))

    posts = Post.get_by_user(user_id)
    return render_template("articles/author.html", author=author, posts=posts)


@articles_bp.route("/<int:post_id>")
def view_article(post_id):
    post = Post.get_by_id(post_id)
    if not post:
        flash("المقال غير موجود.", "error")
        return redirect(url_for('articles.list_articles'))

    comments = Comments.get_comments_by_post(post_id)
    return render_template("articles/detail.html", post=post, comments=comments)


@articles_bp.route("/new", methods=["GET", "POST"])
@limiter.limit("5 per hour")
def new_article():
    if 'user_id' not in session:
        return redirect(url_for('loading_bp.login'))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()

        if not title or not content:
            flash("يرجى كتابة عنوان ومحتوى للمقال.", "error")
            return render_template("articles/form.html", post=None)

        image_path, error = _save_article_image(request.files.get("image"))
        if error:
            flash(error, "error")
            return render_template("articles/form.html", post=None)

        new_post = Post(user_id=session['user_id'], title=title, content=content, image_path=image_path)
        post_id = new_post.add()

        flash("✅ تم نشر المقال بنجاح!", "success")
        return redirect(url_for('articles.view_article', post_id=post_id))

    return render_template("articles/form.html", post=None)


@articles_bp.route("/edit/<int:post_id>", methods=["GET", "POST"])
def edit_article(post_id):
    if 'user_id' not in session:
        return redirect(url_for('loading_bp.login'))

    post = Post.get_by_id(post_id)
    if not post:
        flash("المقال غير موجود.", "error")
        return redirect(url_for('articles.list_articles'))

    user_id = session['user_id']
    if post['user_id'] != user_id and session.get('role') != 'admin':
        flash("لا تملك صلاحية تعديل هذا المقال.", "error")
        return redirect(url_for('articles.view_article', post_id=post_id))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()

        if not title or not content:
            flash("يرجى كتابة عنوان ومحتوى للمقال.", "error")
            return render_template("articles/form.html", post=post)

        image_path, error = _save_article_image(request.files.get("image"))
        if error:
            flash(error, "error")
            return render_template("articles/form.html", post=post)

        Post.update(post_id, title, content, image_path)
        flash("✅ تم تحديث المقال.", "success")
        return redirect(url_for('articles.view_article', post_id=post_id))

    return render_template("articles/form.html", post=post)


@articles_bp.route("/delete/<int:post_id>", methods=["POST"])
def delete_article(post_id):
    if 'user_id' not in session:
        return redirect(url_for('loading_bp.login'))

    user_id = session['user_id']
    user_role = session.get('role', 'user')

    if Post.delete_post(post_id, user_id, user_role):
        flash("🗑 تم حذف المقال.", "success")
    else:
        flash("فشل حذف المقال أو لا تملك الصلاحية.", "error")

    return redirect(url_for('articles.list_articles'))


@articles_bp.route("/<int:post_id>/comment", methods=["POST"])
@limiter.limit("10 per minute")
def add_comment(post_id):
    if 'user_id' not in session:
        return redirect(url_for('loading_bp.login'))

    content = request.form.get("content", "").strip()
    if len(content) < 2:
        flash("التعليق قصير جداً.", "error")
        return redirect(url_for('articles.view_article', post_id=post_id))

    Comments.add_comment(user_id=session['user_id'], content=content, post_id=post_id)
    return redirect(url_for('articles.view_article', post_id=post_id))


@articles_bp.route("/comment/delete/<int:comment_id>/<int:post_id>", methods=["POST"])
def delete_comment(comment_id, post_id):
    if 'user_id' not in session:
        return redirect(url_for('loading_bp.login'))

    Comments.delete_comment(comment_id, session['user_id'], session.get('role', 'user'))
    return redirect(url_for('articles.view_article', post_id=post_id))
