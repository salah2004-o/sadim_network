from app.__init__ import app
from werkzeug.middleware.proxy_fix import ProxyFix

#app.wsgi_app = ProxyFix(
#    app.wsgi_app,
#    x_for=1,
#    x_proto=1,
#    x_host=1
#)

if __name__ == "__main__":
    # use_reloader=False: الـ reloader يشغّل الملف مرتين (عملية مراقبة + عملية تشغيل فعلية)،
    # وبما إن البوتات تشتغل عند استيراد التطبيق، هذا يسبب تشغيل نفس البوت مرتين وتضارب مع تيليجرام (409 Conflict)
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)