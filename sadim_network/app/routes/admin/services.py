# file services adimn
from flask import session, render_template, request, redirect, url_for, flash
from datetime import datetime
from app.routes.admin.admin import admin_bp
from utlis.login_required import login_required
from utlis.permissions import admin_required
from werkzeug.utils import secure_filename
import os
from app.routes.shared import UPLOAD_FOLDER, allowed_file, BASE_DIR
from app.utlis.timezone_utils import Timezone

from app.models.product import service
import pytz

@admin_bp.route("/serverss")
@login_required
@admin_required
def services_dashboard():
    
    username = session.get('username', 'ضيف')

    current_time, greeting = Timezone.get_time_and_greeting()

    # جلب الخدمات من قاعدة البيانات
    services = service.get_all_services()

    # اختبار ما تم جلبه
    print("Services:", services)

    return render_template("dashboard/services_dashboard.html", services=services, username=username, greeting=greeting, current_time=current_time)


# ------------------ صفحة عرض جميع الخدمات ------------------
@admin_bp.route('/services')
def show_services():
#    if 'user_id' not in session:
#        flash("يرجى تسجيل الدخول للوصول إلى الخدمات.", "warning")
#        return redirect(url_for('loading_bp.login_page'))
    
    books = service.get_all_books()
    tech_tools = service.get_all_tech_tools()
    
    # اسم المستخدم من session
    username = session.get('username', 'ضيف')

    # الوقت الحالي حسب منطقتك
    tz = pytz.timezone("Africa/Tripoli")
    now = datetime.now(tz)
    current_time = now.strftime("%Y-%m-%d")

    # تحديد التحية حسب الوقت
    hour = now.hour
    if 5 <= hour < 12:
        greeting = "صباح الخير"
    elif 12 <= hour < 17:
        greeting = "مساء النور"
    else:
        greeting = "مساء الخير"

    return render_template('dashboard/services.html', books=books, tech_tools=tech_tools,
                         username=username, greeting=greeting, current_time=current_time)


# ------------------ صفحة إضافة خدمة جديدة ------------------
@admin_bp.route('/services/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_service():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        price = request.form['price']
        delivery_time = request.form['delivery_time']
        category = request.form.get('category', 'tech')  # استلام التصنيف الجديد

        # التعامل مع الصورة (نفس كودك الحالي)
        image_file = request.files.get('image')

        if image_file and image_file.filename != '':

            filename = secure_filename(image_file.filename)
            image_file.save(os.path.join(UPLOAD_FOLDER, filename))
            image_url = f'uploads/{filename}'
        else:
            image_url = 'uploads/default.jpg'
 
        # إدخال البيانات مع التصنيف
        service.add_service(image_url, title, category, description, title, price, delivery_time)  # تمرير التصنيف الجديد

        
        flash('✅ تمت إضافة الخدمة بنجاح!', 'success')
        return redirect(url_for('admin.add_service'))

    return render_template('dashboard/service_form.html', service=None)
# ------------------ صفحة تعديل خدمة ------------------
@admin_bp.route('/services/edit/<int:service_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_service(service_id):

    if request.method == 'POST':
        
        title = request.form['title']
        description = request.form['description']
        price = request.form['price']
        image_url = request.form.get('image_url')
        delivery_time = request.form['delivery_time']
        category = request.form.get('category') # الخطوة 1: استلام النوع

        service.update_service(service_id, image_url,  description, title, price, delivery_time, category)  # الخطوة 2: تمرير النوع
        flash('تم تحديث الخدمة بنجاح!', 'success')
        return redirect(url_for('admin.show_services'))

    # عرض البيانات في النموذج للتعديل
    current_service = service.get_service(service_id)

    return render_template('dashboard/service_form.html', service=current_service)


# ------------------ حذف خدمة ------------------
@admin_bp.route('/services/delete/<int:service_id>')
@login_required
@admin_required
def delete_service(service_id):
    service.delete_service(service_id)
    flash('تم حذف الخدمة بنجاح!', 'danger')
    return redirect(url_for('admin.services_dashboard'))

@admin_bp.route('/service/<string:type>/<int:item_id>')
def service_detail(type, item_id):
    item = None
    if type == 'book':
        item = service.get_book_by_id(item_id) # افترضت اسم النموذج Book
    elif type == 'tool':
        item = service.get_tool_by_id(item_id) # افترضت اسم النموذج TechTool

    return render_template('dashboard/s.html', item=item, type=type)

