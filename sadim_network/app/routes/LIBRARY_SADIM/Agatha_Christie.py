from flask import (
    Blueprint,
    render_template,
    url_for,
    session,
    redirect,
    send_from_directory,
    request,
    flash
)
from app.limiter import limiter
from app.db.sadim_db import get_db_connection
import os
from psycopg2.extras import RealDictCursor
import psycopg2.extras
from app.models.library_mdl import Library
from app.models.user import User
from app.models.comments import Comments  # تأكد من استيراد المودل الذي صممناه سابقاً
from app.models.analytics_model import log_event
from flask import g
# إنشاء البلوبرينت مع تحديد مجلد الملفات الثابتة بشكل صريح
Library_Agatha_bp = Blueprint(
    'Library_Agatha',
    __name__,
    template_folder='templates',
    static_folder='static'
)

# نحدد مكان الملف الحالي
current_dir = os.path.dirname(os.path.abspath(__file__))

# نصعد مستويين فقط للوصول لمجلد app (من LIBRARY_SADIM إلى routes ثم إلى app)
# المستوى 1: .. (يخرج من LIBRARY_SADIM إلى routes)
# المستوى 2: .. (يخرج من routes إلى app)
BASE_DIR = os.path.abspath(os.path.join(current_dir, "..", ".."))

# الآن ندمج المسار مع static/uploads
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')


def _download_limit_key(prefix="download"):
    book_id = request.view_args.get("book_id", "unknown") if request.view_args else "unknown"
    return f"{prefix}:{session.get('user_id', 'guest')}:{request.remote_addr}:{book_id}"


def _log_lib_event(event_type, metadata=None):
    """تسجيل حدث مكتبة بدون أي احتمال لكسر تدفق العرض/التحميل الفعلي لو فشل التسجيل نفسه."""
    try:
        log_event(
            event_type,
            user_id=session.get('user_id'),
            session_id=g.get('sd_session_id'),
            ip=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
            path=request.path,
            referrer=request.referrer,
            visitor_type=g.get('sd_visitor_type', 'unknown'),
            metadata=metadata,
        )
    except Exception as e:
        print(f"Failed to log analytics event '{event_type}':", e)

# =========================
# عرض المكتبة للجمهور
# =========================
@Library_Agatha_bp.route('/library/agatha_christie')
@limiter.limit("5 per minute")

def agatha_christie():
    # التحقق من تسجيل الدخول (اختياري حسب رغبتك)
#    if 'user_id' not in session:
#        return redirect(url_for('loading_bp.login'))

    sort = request.args.get('sort', 'downloads')
    order_sql = {
        'downloads': "ORDER BY download_count DESC NULLS LAST",
        'newest': "ORDER BY id DESC",
    }.get(sort, "ORDER BY download_count DESC NULLS LAST")

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    # جلب جميع الكتب لعرضها
    cur.execute(f"SELECT * FROM books {order_sql};")

    books = cur.fetchall()

    cur.close()
    conn.close()

    comment_counts = Comments.get_book_comment_counts()
    if sort == 'discussed':
        books = sorted(books, key=lambda b: comment_counts.get(b['id'], 0), reverse=True)

    total_downloads = sum(b['download_count'] or 0 for b in books)
    total_comments = sum(comment_counts.values())
    recent_discussions = Comments.get_recent_book_discussions(limit=6)

    _log_lib_event("library.view", metadata={"sort": sort, "books_count": len(books)})

    user = User.get_by_id(session['user_id']) if 'user_id' in session else None
    return render_template(
        "Agatha Christie/Agatha.html",
        books=books, user=user, sort=sort,
        comment_counts=comment_counts,
        total_downloads=total_downloads,
        total_comments=total_comments,
        recent_discussions=recent_discussions,
    )


@Library_Agatha_bp.route("/Library/Agatha_Christie/<int:book_id>")
@limiter.limit("5 per minute")
def view_book(book_id):
    book = Library.get_book_id(book_id)

    if not book:
        return "الكتاب غير موجود", 404

    # جلب التعليقات الخاصة بهذا الكتاب
    # ملاحظة: يفضل تعديل ميثود get_comments_by_book في المودل لتجلب اسم المستخدم بـ Join
    comments = Comments.get_comments_by_book(book_id)
    other_books = Library.get_other_books(book_id, limit=4)

    _log_lib_event("book.view", metadata={"book_id": book_id, "title": book.get('title')})

    user = User.get_by_id(session['user_id']) if 'user_id' in session else None
    return render_template(
        "Agatha Christie/book_detail.html",
        book=book,
        comments=comments,
        other_books=other_books,
        user=user
    )
# =========================
# 2. تحميل الملف الفعلي — طلب واحد ذرّي: يتحقق من الملف، يزيد العداد، يسجّل الحدث، ثم يرسل الملف.
# لا يعتمد على أي طلب منفصل قبله (كان فيه طلبان غير مرتبطين: زيادة عداد + تحميل فعلي، ممكن الأول
# ينجح دون الثاني). العداد وحدث download.success الآن لا يُسجَّلان إلا لو الملف فعلاً موجود ووصل للمستخدم.
# =========================
@Library_Agatha_bp.route('/library/download/<int:book_id>')
@limiter.limit("10 per hour", key_func=_download_limit_key)
def download_file(book_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT title, pdf_path FROM books WHERE id = %s", (book_id,))
    book = cur.fetchone()

    cur.close()
    conn.close()

    if not book:
        _log_lib_event("download.failed", metadata={"book_id": book_id, "reason": "book_not_found"})
        return "الكتاب غير موجود في قاعدة البيانات", 404

    file_path = os.path.join(UPLOAD_FOLDER, book['pdf_path'])
    if not os.path.exists(file_path):
        _log_lib_event("download.failed", metadata={
            "book_id": book_id, "title": book.get('title'), "reason": "file_missing_on_server"
        })
        return "الملف غير موجود على السيرفر", 404

    conn2 = get_db_connection()
    cur2 = conn2.cursor()
    cur2.execute(
        "UPDATE books SET download_count = COALESCE(download_count, 0) + 1 WHERE id = %s RETURNING download_count",
        (book_id,)
    )
    new_count = cur2.fetchone()[0]
    conn2.commit()
    cur2.close()
    conn2.close()

    _log_lib_event("download.success", metadata={
        "book_id": book_id, "title": book.get('title'), "file": book['pdf_path'], "new_count": new_count
    })

    return send_from_directory(
        UPLOAD_FOLDER,
        book['pdf_path'],
        as_attachment=True,
        download_name=f"{book['title']}.pdf"
    )

# =========================
# 1. [قديم/متروك] تحديث عداد التحميلات المستقل — تسبَّب بمشكلة عدّ غير دقيق (يزيد العداد
# حتى لو فشل التحميل الفعلي بعده). العداد الآن جزء من download_file() نفسها (طلب واحد ذرّي).
# الراوت باقٍ فقط توافقاً مع أي استدعاء قديم مخزَّن بمتصفح، لا يُستدعى من أي قالب حالياً.
# =========================
@Library_Agatha_bp.route('/library/increment_download/<int:book_id>', methods=['POST'])
@limiter.limit("2 per hour", key_func=lambda: _download_limit_key("legacy"))
def increment_download(book_id):
    return {"success": False, "error": "deprecated"}, 410

# =========================
# 3. البحث (تمت إضافة حقل download_count)
# =========================
@Library_Agatha_bp.route('/search')
def search():
    query = request.args.get('q', '')

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # أضفنا id و cover_path و download_count لتعمل نتائج البحث بنفس كفاءة الصفحة الرئيسية
    cur.execute("""
        SELECT id, title, desc_text, pdf_path, cover_path, download_count
        FROM books
        WHERE title ILIKE %s
        ORDER BY id DESC
    """, (f"%{query}%",))

    books = cur.fetchall()

    cur.close()
    conn.close()

    _log_lib_event("book.search", metadata={"query": query, "results_count": len(books)})

    return render_template(
        "Agatha Christie/search_results.html",
        query=query,
        books=books
    )


# =========================
# 3-ب. بحث فوري (Live/Typeahead) — معاينة سريعة فقط بالرئيسية، بدون تسجيل حدث تحليلي
# (البحث "الحقيقي" اللي يُسجَّل بالتحليلات يبقى فقط عبر /search أعلاه عند الضغط فعلياً على نتيجة/إرسال النموذج)
# =========================
@Library_Agatha_bp.route('/library/quick_search')
def quick_search():
    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return {"results": []}

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT id, title, cover_path
        FROM books
        WHERE title ILIKE %s
        ORDER BY download_count DESC NULLS LAST
        LIMIT 5
    """, (f"%{query}%",))
    books = cur.fetchall()
    cur.close()
    conn.close()

    return {"results": [
        {
            "id": b["id"],
            "title": b["title"],
            "cover_url": url_for('Library_Agatha.static', filename='uploads/' + b["cover_path"]) if b["cover_path"] else None,
            "url": url_for('Library_Agatha.view_book', book_id=b["id"]),
        }
        for b in books
    ]}


# =========================
# إضافة تعليق جديد
# =========================
@Library_Agatha_bp.route('/library/add_comment/<int:book_id>', methods=['POST'])
def add_comment(book_id):
    if 'user_id' not in session:
        flash("يجب تسجيل الدخول لإضافة تعليق.", "danger")
        return redirect(url_for('loading_bp.login')) # تأكد من اسم روت تسجيل الدخول لديك

    content = request.form.get('content')
    user_id = session['user_id']

    if not content or len(content.strip()) < 2:
        flash("محتوى التعليق قصير جداً.", "warning")
        return redirect(url_for('Library_Agatha.view_book', book_id=book_id))

    result = Comments.add_comment(user_id=user_id, content=content, book_id=book_id)
    
    if result['status'] == 'success':
        flash("تم نشر تعليقك بنجاح.", "success")
    else:
        flash(f"فشل نشر التعليق: {result['message']}", "danger")

    return redirect(url_for('Library_Agatha.view_book', book_id=book_id))

@Library_Agatha_bp.route('/library/delete_comment/<int:comment_id>/<int:book_id>')
def delete_comment(comment_id, book_id):
    if 'user_id' not in session:
        return redirect(url_for('loading_bp.login'))
    
    if Comments.delete_comment(comment_id, session['user_id'], session.get('role', 'user')):
        flash("تم حذف التعليق بنجاح", "success")
    else:
        flash("لا تملك صلاحية حذف هذا التعليق", "danger")
        
    return redirect(url_for('Library_Agatha.view_book', book_id=book_id))