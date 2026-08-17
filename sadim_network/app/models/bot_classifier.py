"""تصنيف الزائر: human | bot | crawler | scanner | unknown — بدمج عدة إشارات مستقلة،
لا الاعتماد على User-Agent وحده (طلب صريح: نفس أداة فحص ثغرات يقدر يضع أي User-Agent يريده)."""

from app.config import settings

# زواحف شرعية معروفة (محركات بحث، معاينات روابط) — تُصنَّف "crawler" منفصلة عن "bot" العام
_KNOWN_CRAWLERS = (
    "googlebot", "bingbot", "yandexbot", "duckduckbot", "baiduspider",
    "facebookexternalhit", "twitterbot", "linkedinbot", "telegrambot",
    "slackbot", "whatsapp", "applebot", "google-read-aloud",
)

# أدوات/سكربتات آلية عامة — مو زاحف محرك بحث شرعي، لكن مو بالضرورة عدائي
_GENERIC_BOT_MARKERS = (
    "bot", "spider", "crawl", "curl", "python-requests", "wget",
    "scrapy", "libwww", "go-http-client", "httpclient", "axios",
)

# أنماط مسارات لا يطلبها إلا سكانر يفحص ثغرات معروفة — هذا المشروع Flask بلا أي مسار مشابه فعلياً
_SCANNER_PATH_PATTERNS = (
    "/wp-admin", "/wp-login", "/wp-content", "/wp-json", "/xmlrpc.php",
    "/.env", "/.git", "/.aws", "/.ssh", "/config.json", "/phpmyadmin",
    "/administrator", "/admin.php", "/vendor/phpunit", "/_profiler",
    "/actuator", "/.well-known/security.txt", "/eval-stdin.php",
)

BURST_THRESHOLD = 40        # عدد طلبات
BURST_WINDOW_SECONDS = 60   # خلال هذه المدة => معدّل غير بشري من نفس IP


def _is_scanner_path(path):
    path_lower = (path or "").lower()
    return any(pattern in path_lower for pattern in _SCANNER_PATH_PATTERNS)


def _is_request_burst(ip):
    """معدّل طلبات مرتفع من نفس IP خلال دقيقة — إشارة سلوكية مستقلة تماماً عن الـUA المُعلَن.
    يعتمد على نفس Redis المستخدم أصلاً لأقفال البوتات؛ لو غير متاح (تطوير محلي) يرجّع False بأمان بدل الانهيار."""
    if not ip or not settings.SESSION_REDIS:
        return False
    try:
        key = f"sadim:analytics:burst:{ip}"
        count = settings.SESSION_REDIS.incr(key)
        if count == 1:
            settings.SESSION_REDIS.expire(key, BURST_WINDOW_SECONDS)
        return count > BURST_THRESHOLD
    except Exception:
        return False


def classify_visitor(path, user_agent, ip, headers=None):
    headers = headers or {}
    ua = (user_agent or "").strip()
    ua_lower = ua.lower()

    # إشارة قاطعة أولاً: نمط مسار سكانر معروف، بغض النظر عن الـUA المُعلَن
    if _is_scanner_path(path):
        return "scanner"

    if not ua:
        return "unknown"

    if any(marker in ua_lower for marker in _KNOWN_CRAWLERS):
        return "crawler"

    if any(marker in ua_lower for marker in _GENERIC_BOT_MARKERS):
        return "bot"

    if _is_request_burst(ip):
        return "bot"

    # رؤوس متصفح ناقصة كلياً (لا Accept-Language ولا Accept) — إشارة ضعيفة بمفردها، تكفي فقط لتصنيف "unknown"
    if not headers.get("Accept-Language") and not headers.get("Accept"):
        return "unknown"

    return "human"
