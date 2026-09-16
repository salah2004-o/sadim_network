import os
import time
import secrets

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    g,
)

from werkzeug.utils import secure_filename
from PIL import Image

from app.routes.shared import UPLOAD_FOLDER, allowed_file
from app.limiter import limiter
from app.models.post_model import Post
from app.models.comments import Comments
from app.models.user import User
from app.models.analytics_model import log_event


articles_bp = Blueprint(
    "articles",
    __name__,
    url_prefix="/articles"
)


MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 ميجا
POSTS_PER_PAGE = 10


def _log_article_event(event_type, metadata=None):
    """
    تسجيل حدث منشور بدون التأثير على تدفق الصفحة
    في حال فشل نظام التحليلات.
    """
    try:
        log_event(
            event_type,
            user_id=session.get("user_id"),
            session_id=g.get("sd_session_id"),
            ip=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
            path=request.path,
            visitor_type=g.get("sd_visitor_type", "unknown"),
            metadata=metadata,
        )
    except Exception as e:
        print(
            f"Failed to log analytics event "
            f"'{event_type}':",
            e
        )


def _get_article_feed_seed():
    """
    Seed ثابت للزائر الحالي.

    الهدف:
    - كل زائر يحصل على ترتيب مختلف.
    - Refresh لا يعيد ترتيب المنشورات.
    - الانتقال بين الصفحات يحافظ على نفس الترتيب.
    """
    seed = session.get("articles_feed_seed")

    if seed is None:
        seed = secrets.randbits(31)
        session["articles_feed_seed"] = seed

    return seed


def _save_article_image(file_storage):
    """
    التحقق من الصورة فعلياً، ثم إعادة ترميزها بواسطة Pillow
    وإزالة بيانات EXIF والمحتوى المخفي قدر الإمكان.

    يرجع:
        (relative_path, None)
    عند النجاح.

        (None, error_message)
    عند الفشل.
    """

    if not file_storage or file_storage.filename == "":
        return None, None

    if not allowed_file(file_storage.filename):
        return None, "امتداد الملف غير مسموح."

    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)

    if size > MAX_IMAGE_SIZE:
        return None, "حجم الصورة أكبر من الحد المسموح (٥ ميجا)."

    try:
        img = Image.open(file_storage.stream)
        img.verify()
    except Exception:
        return None, "الملف المرفوع ليس صورة صالحة."

    # verify() يستهلك الملف، لذلك نعيد فتحه.
    file_storage.stream.seek(0)

    try:
        img = Image.open(file_storage.stream)

        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")

        filename = secure_filename(
            f"post_{int(time.time() * 1000)}.jpg"
        )

        full_path = os.path.join(
            UPLOAD_FOLDER,
            filename
        )

        img.save(
            full_path,
            "JPEG",
            quality=85
        )

    except Exception as e:
        print("Failed to save article image:", e)
        return None, "تعذر حفظ الصورة."

    return f"uploads/{filename}", None


# =========================================================
# قائمة المنشورات
# =========================================================

@articles_bp.route("/")
def list_articles():
    """
    عرض المنشورات مع:
    - Pagination
    - البحث
    - ترتيب شخصي لكل زائر
    - المنشور المميز
    - الأكثر نقاشاً
    """

    # حماية بسيطة من قيم page غير الصالحة.
    try:
        page = int(request.args.get("page", 1))
    except (TypeError, ValueError):
        page = 1

    page = max(page, 1)

    # البحث
    search_query = request.args.get("q", "").strip()

    offset = (page - 1) * POSTS_PER_PAGE

    # Seed ثابت للزائر.
    feed_seed = _get_article_feed_seed()

    # جلب المنشورات.
    #
    # سيتم تعديل Post.get_all لاحقاً ليدعم:
    # search=
    # feed_seed=
    posts = Post.get_all(
        limit=POSTS_PER_PAGE,
        offset=offset,
        search=search_query or None,
        feed_seed=feed_seed,
    )

    # العدد الإجمالي بعد تطبيق البحث.
    total = Post.get_count(
        search=search_query or None
    )

    has_next = (
        offset + POSTS_PER_PAGE < total
    )

    has_prev = page > 1

    # التعليقات
    comment_counts = (
        Comments.get_post_comment_counts()
    )

    # =====================================================
    # المنشور المميز
    # =====================================================

    featured = None
    feed_posts = posts

    # لا نعرض المنشور المميز في نتائج البحث.
    if not search_query and page == 1 and posts:
        featured = posts[0]
        feed_posts = posts[1:]

    # =====================================================
    # الأكثر نقاشاً
    # =====================================================

    most_discussed = sorted(
        posts,
        key=lambda p: comment_counts.get(
            p["id"],
            0
        ),
        reverse=True
    )[:3]

    return render_template(
        "articles/list.html",

        # البيانات الأساسية
        posts=posts,
        feed_posts=feed_posts,

        # pagination
        page=page,
        has_next=has_next,
        has_prev=has_prev,

        # featured
        featured=featured,

        # discussions
        comment_counts=comment_counts,
        most_discussed=most_discussed,

        # البحث
        search_query=search_query,
    )


# =========================================================
# صفحة الكاتب
# =========================================================

@articles_bp.route("/author/<int:user_id>")
def author_profile(user_id):
    author = User.get_by_id(user_id)

    if not author:
        flash(
            "الكاتب غير موجود.",
            "error"
        )
        return redirect(
            url_for("articles.list_articles")
        )

    posts = Post.get_by_user(user_id)

    return render_template(
        "articles/author.html",
        author=author,
        posts=posts
    )


# =========================================================
# عرض منشور
# =========================================================

@articles_bp.route("/<int:post_id>")
def view_article(post_id):
    post = Post.get_by_id(post_id)

    if not post:
        flash(
            "المنشور غير موجود.",
            "error"
        )
        return redirect(
            url_for("articles.list_articles")
        )

    # -----------------------------------------------------
    # تسجيل مشاهدة المنشور
    # -----------------------------------------------------
    #
    # Post.register_view() ستكون مسؤولة عن:
    # - زيادة views
    # - منع احتساب Refresh المتكرر
    # - التعامل مع session/user/IP
    #
    try:
        Post.register_view(
            post_id=post_id,
            session_id=g.get("sd_session_id"),
            user_id=session.get("user_id"),
            ip=request.remote_addr,
        )
    except Exception as e:
        # عداد المشاهدات لا يجب أن يمنع فتح المنشور.
        print(
            f"Failed to register article view "
            f"for post {post_id}:",
            e
        )

    comments = Comments.get_comments_by_post(
        post_id
    )

    related_posts = Post.get_recent(
        limit=4,
        exclude_id=post_id
    )

    # Analytics منفصل عن عداد views.
    _log_article_event(
        "article.view",
        metadata={
            "post_id": post_id,
            "title": post.get("title"),
        }
    )

    # إعادة جلب المنشور حتى نحصل على views
    # بعد تسجيل المشاهدة.
    updated_post = Post.get_by_id(post_id)

    if updated_post:
        post = updated_post

    return render_template(
        "articles/detail.html",
        post=post,
        comments=comments,
        related_posts=related_posts,
    )


# =========================================================
# إنشاء منشور
# =========================================================

@articles_bp.route(
    "/new",
    methods=["GET", "POST"]
)
@limiter.limit("5 per hour")
def new_article():

    if "user_id" not in session:
        return redirect(
            url_for("loading_bp.login")
        )

    if request.method == "POST":

        title = request.form.get(
            "title",
            ""
        ).strip()

        content = request.form.get(
            "content",
            ""
        ).strip()

        if not title or not content:
            flash(
                "يرجى كتابة عنوان ومحتوى للمنشور.",
                "error"
            )

            return render_template(
                "articles/form.html",
                post=None
            )

        image_path, error = _save_article_image(
            request.files.get("image")
        )

        if error:
            flash(
                error,
                "error"
            )

            return render_template(
                "articles/form.html",
                post=None
            )

        new_post = Post(
            user_id=session["user_id"],
            title=title,
            content=content,
            image_path=image_path
        )

        post_id = new_post.add()

        flash(
            "تم نشر المنشور بنجاح.",
            "success"
        )

        return redirect(
            url_for(
                "articles.view_article",
                post_id=post_id
            )
        )

    return render_template(
        "articles/form.html",
        post=None
    )


# =========================================================
# تعديل منشور
# =========================================================

@articles_bp.route(
    "/edit/<int:post_id>",
    methods=["GET", "POST"]
)
def edit_article(post_id):

    if "user_id" not in session:
        return redirect(
            url_for("loading_bp.login")
        )

    post = Post.get_by_id(post_id)

    if not post:
        flash(
            "المنشور غير موجود.",
            "error"
        )

        return redirect(
            url_for("articles.list_articles")
        )

    user_id = session["user_id"]

    if (
        post["user_id"] != user_id
        and session.get("role") != "admin"
    ):
        flash(
            "لا تملك صلاحية تعديل هذا المنشور.",
            "error"
        )

        return redirect(
            url_for(
                "articles.view_article",
                post_id=post_id
            )
        )

    if request.method == "POST":

        title = request.form.get(
            "title",
            ""
        ).strip()

        content = request.form.get(
            "content",
            ""
        ).strip()

        if not title or not content:
            flash(
                "يرجى كتابة عنوان ومحتوى للمنشور.",
                "error"
            )

            return render_template(
                "articles/form.html",
                post=post
            )

        image_path, error = _save_article_image(
            request.files.get("image")
        )

        if error:
            flash(
                error,
                "error"
            )

            return render_template(
                "articles/form.html",
                post=post
            )

        Post.update(
            post_id,
            title,
            content,
            image_path
        )

        flash(
            "تم تحديث المنشور.",
            "success"
        )

        return redirect(
            url_for(
                "articles.view_article",
                post_id=post_id
            )
        )

    return render_template(
        "articles/form.html",
        post=post
    )


# =========================================================
# حذف منشور
# =========================================================

@articles_bp.route(
    "/delete/<int:post_id>",
    methods=["POST"]
)
def delete_article(post_id):

    if "user_id" not in session:
        return redirect(
            url_for("loading_bp.login")
        )

    user_id = session["user_id"]
    user_role = session.get(
        "role",
        "user"
    )

    if Post.delete_post(
        post_id,
        user_id,
        user_role
    ):
        flash(
            "تم حذف المنشور.",
            "success"
        )
    else:
        flash(
            "فشل حذف المنشور أو لا تملك الصلاحية.",
            "error"
        )

    return redirect(
        url_for("articles.list_articles")
    )


# =========================================================
# إضافة تعليق
# =========================================================

@articles_bp.route(
    "/<int:post_id>/comment",
    methods=["POST"]
)
@limiter.limit("10 per minute")
def add_comment(post_id):

    if "user_id" not in session:
        return redirect(
            url_for("loading_bp.login")
        )

    content = request.form.get(
        "content",
        ""
    ).strip()

    if len(content) < 2:
        flash(
            "التعليق قصير جداً.",
            "error"
        )

        return redirect(
            url_for(
                "articles.view_article",
                post_id=post_id
            )
        )

    Comments.add_comment(
        user_id=session["user_id"],
        content=content,
        post_id=post_id
    )

    return redirect(
        url_for(
            "articles.view_article",
            post_id=post_id
        )
    )


# =========================================================
# حذف تعليق
# =========================================================

@articles_bp.route(
    "/comment/delete/<int:comment_id>/<int:post_id>",
    methods=["POST"]
)
def delete_comment(
    comment_id,
    post_id
):

    if "user_id" not in session:
        return redirect(
            url_for("loading_bp.login")
        )

    Comments.delete_comment(
        comment_id,
        session["user_id"],
        session.get("role", "user")
    )

    return redirect(
        url_for(
            "articles.view_article",
            post_id=post_id
        )
    )