from xml.sax.saxutils import escape

from flask import Blueprint, Response, request, url_for

from app.db.sadim_db import get_db_connection

seo_bp = Blueprint('seo', __name__)


def canonical_url():
    """رابط الصفحة بدون أي query (ref=share، utm، sort...) — عدا رقم الصفحة في القوائم المقسّمة
    (توصية Google: الصفحة 2 لها canonical لنفسها، لا للصفحة الأولى)."""
    page = request.args.get('page', type=int)
    if page and page > 1:
        return f"{request.base_url}?page={page}"
    return request.base_url


# مسارات خاصة أو بلا قيمة بحثية. ملفات PDF تُستثنى (التحميل والقراءة عبر صفحات الكتاب)،
# أما الأغلفة في نفس المجلد فتبقى متاحة لأنها صورة og:image وSchema.
_DISALLOW = (
    "/dashboard", "/profile", "/api/", "/auth/", "/account", "/landing", "/logout",
    "/resend_verification", "/verify_email", "/menu",
    "/ai/conversations", "/ai/guest", "/ai/summarize", "/ai/providers",
    "/library/search", "/library/quick_search", "/library/*/download", "/library/download/",
    "/library/add_comment", "/library/delete_comment", "/library/increment_download",
    "/static/uploads/*.pdf$",
)


@seo_bp.route('/robots.txt')
def robots_txt():
    # مجموعة * تشمل Googlebot وBingbot — لا مجموعات خاصة بهما حتى لا تُلغي قواعد * عنهما
    lines = ["User-agent: *", "Allow: /"]
    lines += [f"Disallow: {path}" for path in _DISALLOW]
    lines += ["", f"Sitemap: {url_for('seo.sitemap_xml', _external=True)}", ""]
    response = Response("\n".join(lines), mimetype="text/plain")
    response.headers["Cache-Control"] = "public, max-age=86400"
    return response


@seo_bp.route('/sitemap.xml')
def sitemap_xml():
    entries = [
        (url_for('main.index', _external=True), None, "daily", "1.0"),
        (url_for('library.library', _external=True), None, "daily", "0.9"),
        (url_for('articles.list_articles', _external=True), None, "daily", "0.8"),
        (url_for('main.discover', _external=True), None, "weekly", "0.6"),
        (url_for('main.services', _external=True), None, "weekly", "0.5"),
        (url_for('main.about', _external=True), None, "monthly", "0.4"),
    ]
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM books ORDER BY id")
        for (book_id,) in cur.fetchall():
            entries.append((url_for('library.view_book', book_id=book_id, _external=True), None, "weekly", "0.8"))
        cur.execute("SELECT id, COALESCE(updated_at, created_at) FROM posts ORDER BY id")
        for post_id, modified in cur.fetchall():
            entries.append((url_for('articles.view_article', post_id=post_id, _external=True), modified, "monthly", "0.7"))
    finally:
        conn.close()

    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, lastmod, changefreq, priority in entries:
        parts.append("<url>")
        parts.append(f"<loc>{escape(loc)}</loc>")
        if lastmod:
            parts.append(f"<lastmod>{lastmod.date().isoformat()}</lastmod>")
        parts.append(f"<changefreq>{changefreq}</changefreq><priority>{priority}</priority>")
        parts.append("</url>")
    parts.append("</urlset>")
    response = Response("\n".join(parts), mimetype="application/xml")
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response
