from app.routes.admin.admin import admin_bp
from app.routes.shared import UPLOAD_FOLDER, allowed_file
from app.db.sadim_db import get_db_connection

from utlis.permissions import admin_required
from utlis.login_required import login_required
from app.utlis.apply_sadim_brand import apply_sadim_brand

import psycopg2
import threading
import time
import os
from app.config import settings
from app.models import shelf_model
from flask import render_template, request, redirect, url_for, flash
from models.library_mdl import Library
# ==========================================
# قسم إدارة المكتبة (الدمج الجديد)
# ==========================================
@admin_bp.route('/library/manage')
@login_required
@admin_required
def manage_library():
    """عرض الكتب في لوحة التحكم"""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM books ORDER BY id DESC;")
    books = cur.fetchall()
    cur.close()
    conn.close()

    return render_template("dashboard/admin_dashboard.html", books=books)
# إضافة كتاب جديد للمكتبة
@admin_bp.route('/library/add', methods=['POST'])
@login_required
@admin_required
def add_book_to_library():
    title = request.form.get('title')
    desc = request.form.get('desc')
    pdf = request.files.get('pdf_file')
    cover = request.files.get('cover_file')

    if not all([title, pdf, cover]):
        flash("❌ خطأ: جميع الحقول مطلوبة", "danger")
        return redirect(url_for('admin.manage_library'))

    if allowed_file(pdf.filename) and allowed_file(cover.filename):
        # استخراج الامتدادات
        pdf_ext = pdf.filename.rsplit('.', 1)[1].lower() # نستخدم rsplit لتجنب مشاكل الأسماء التي تحتوي على نقاط و كذلك لتحديد الامتداد بشكل صحيح
        cover_ext = cover.filename.rsplit('.', 1)[1].lower()

        # توليد اسم فريد للسيرفر (بصمة زمنية) لتجنب مشاكل العربي والملفات المتكررة
        timestamp = int(time.time())
        pdf_name = f"sadim_{timestamp}.{pdf_ext}"
        cover_name = f"cover_{timestamp}.{cover_ext}"

        pdf_full_path = os.path.join(UPLOAD_FOLDER, pdf_name)
        cover_full_path = os.path.join(UPLOAD_FOLDER, cover_name)

        # حفظ الملفات
        pdf.save(pdf_full_path)
        cover.save(cover_full_path)

        # إضافة شعار سديم
        try:
            apply_sadim_brand(pdf_full_path)
        except Exception as e:
            print(f"⚠️ فشل إضافة الشعار: {e}")

        # حفظ البيانات (العنوان العربي سيحفظ في خانة title)
        book_id = Library.add_book(title, desc, pdf_name, cover_name)

        # تنبيه المشتركين بالبريد في خيط خلفي — لا يؤخّر رد لوحة الإدارة ولا يكسرها لو فشل
        app_url = (settings.APP_URL or request.url_root).rstrip('/')
        threading.Thread(
            target=shelf_model.notify_new_book,
            args=(title, f"{app_url}{url_for('library.view_book', book_id=book_id)}",
                  f"{app_url}{url_for('static', filename='uploads/' + cover_name)}", app_url),
            daemon=True,
        ).start()

        flash("✅ تم رفع الرواية بنجاح!", "success")
    else:
        flash("❌ نوع ملف غير مسموح", "warning")

    return redirect(url_for('admin.manage_library'))

# تعديل كتاب في المكتبة
@admin_bp.route('/library/edit/<int:book_id>', methods=['POST'])
@login_required
@admin_required
def edit_book_in_library(book_id):
    """تعديل كتاب في المكتبة مباشرة من لوحة الإدارة"""
    title = request.form.get(f"title-{book_id}")
    desc = request.form.get(f"desc-{book_id}")

    if not title:
        flash("❌ العنوان مطلوب", "danger")
        return redirect(url_for('admin.manage_library'))

    # الملفات المرفوعة (قد تكون None)
    cover = request.files.get(f"cover_file-{book_id}")
    pdf = request.files.get(f"pdf_file-{book_id}")

     # جلب الكتاب الحالي لتحديد الملفات القديمة
    book = Library.get_book_id(book_id) 
    
    cover_name = book['cover_path']
    pdf_name = book['pdf_path']
    timestamp = int(time.time())


    if cover and allowed_file(cover.filename):

        old_cover_path = os.path.join(UPLOAD_FOLDER, cover_name)
        if os.path.exists(old_cover_path):
            os.remove(old_cover_path)

        ext = cover.filename.rsplit('.', 1)[1].lower()
        cover_name = f"cover_{timestamp}.{ext}"
        cover.save(os.path.join(UPLOAD_FOLDER, cover_name))

    if pdf and allowed_file(pdf.filename):
        old_pdf_path = os.path.join(UPLOAD_FOLDER, pdf_name)
        if os.path.exists(old_pdf_path):
            os.remove(old_pdf_path)

        ext = pdf.filename.rsplit('.', 1)[1].lower()
        pdf_name = f"sadim_{timestamp}.{ext}"
        pdf.save(os.path.join(UPLOAD_FOLDER, pdf_name))

        # إضافة شعار سديم للملف الجديد
        try:
            apply_sadim_brand(os.path.join(UPLOAD_FOLDER, pdf_name))
        except Exception as e:
            print(f"⚠️ فشل إضافة الشعار: {e}")

    # تحديث قاعدة البيانات
    Library.edit_book(title, desc, cover_name, pdf_name, book_id)

    flash("✅ تم تحديث بيانات الكتاب بنجاح", "success")
    return redirect(url_for('admin.manage_library'))
# حذف كتاب من المكتبة
@admin_bp.route('/library/delete/<int:book_id>', methods=['POST'])
@login_required
@admin_required
def delete_book_from_library(book_id):
    """حذف كتاب من المكتبة مع ملفاته"""

    book = Library.get_book_id(book_id) # جلب مسارات الملفات القديمة من قاعدة البيانات

    if book:
        # حذف الملفات الفيزيائية
        for key in ['pdf_path', 'cover_path']:
            file_path = os.path.join(UPLOAD_FOLDER, book[key])
            if os.path.exists(file_path):
                os.remove(file_path)

        Library.delete_book(book_id) # حذف السجل من قاعدة البيانات
        flash("🗑️ تم حذف الكتاب وملفاته بنجاح", "danger")

    return redirect(url_for('admin.manage_library'))
