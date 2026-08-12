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
    user = User.get_by_id(session['user_id']) if 'user_id' in session else None
    return render_template(
        "Agatha Christie/book_detail.html",
        book=book,
        comments=comments,
        other_books=other_books,
        user=user
    )
# =========================
# 2. تحميل الملف الفعلي (بدون تحديث العداد هنا)
# =========================
@Library_Agatha_bp.route('/library/download/<int:book_id>')
def download_file(book_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    # نجلب بيانات الكتاب فقط
    cur.execute("SELECT title, pdf_path FROM books WHERE id = %s", (book_id,))
    book = cur.fetchone()
    
    cur.close()
    conn.close()

    if book:
        file_path = os.path.join(UPLOAD_FOLDER, book['pdf_path'])
        if os.path.exists(file_path):
            return send_from_directory(
                UPLOAD_FOLDER, 
                book['pdf_path'], 
                as_attachment=True,
                download_name=f"{book['title']}.pdf"
            )
        return "الملف غير موجود على السيرفر", 404
            
    return "الكتاب غير موجود في قاعدة البيانات", 404

# =========================
# 1. تحديث عداد التحميلات (تفاعل لحظي - JSON)
# =========================
@Library_Agatha_bp.route('/library/increment_download/<int:book_id>', methods=['POST'])
def increment_download(book_id):
#    if 'user_id' not in session:
#       flash("يجب تسجيل الدخول لتحميل الكتب.", "warning")
#       return redirect(url_for('loading_bp.login'))
   
    conn = get_db_connection()
    cur = conn.cursor() # لا نحتاج RealDictCursor هنا لأننا سنعيد قيمة واحدة
    try:
        # نستخدم COALESCE لتفادي الخطأ إذا كانت القيمة NULL، ونعيد القيمة الجديدة فوراً
        cur.execute("""
            UPDATE books 
            SET download_count = COALESCE(download_count, 0) + 1 
            WHERE id = %s 
            RETURNING download_count
        """, (book_id,))
        
        new_count = cur.fetchone()[0]
        conn.commit()
        return {"success": True, "new_count": new_count}
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}, 500
    finally:
        cur.close()
        conn.close()

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

    return render_template(
        "Agatha Christie/search_results.html",
        query=query,
        books=books
    )


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