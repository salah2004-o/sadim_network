"""محلّل User-Agent خفيف الوزن بدون أي مكتبة خارجية جديدة — يكفي لتصنيف device_type/browser/os
الأساسي المطلوب لجداول التحليلات. تصنيف bot هنا مبدئي وبسيط (إشارة واحدة)، التصنيف الكامل
متعدد الإشارات (bot/crawler/scanner/unknown) يُبنى بمرحلة لاحقة منفصلة."""

_BOT_MARKERS = ("bot", "spider", "crawl", "slurp", "facebookexternalhit", "bingpreview", "curl", "python-requests", "wget")


def parse_user_agent(user_agent):
    if not user_agent:
        return {"device_type": "unknown", "browser": "unknown", "os": "unknown"}

    ua = user_agent.lower()

    if any(marker in ua for marker in _BOT_MARKERS):
        device_type = "bot"
    elif "ipad" in ua or ("tablet" in ua and "mobile" not in ua):
        device_type = "tablet"
    elif "mobi" in ua or "android" in ua or "iphone" in ua:
        device_type = "mobile"
    else:
        device_type = "desktop"

    if "edg/" in ua:
        browser = "Edge"
    elif "opr/" in ua or "opera" in ua:
        browser = "Opera"
    elif "chrome" in ua and "chromium" not in ua:
        browser = "Chrome"
    elif "safari" in ua and "chrome" not in ua:
        browser = "Safari"
    elif "firefox" in ua:
        browser = "Firefox"
    else:
        browser = "Other"

    if "windows" in ua:
        os_name = "Windows"
    elif "android" in ua:
        os_name = "Android"
    elif "iphone" in ua or "ipad" in ua or " ios " in f" {ua} ":
        os_name = "iOS"
    elif "mac os" in ua or "macintosh" in ua:
        os_name = "macOS"
    elif "linux" in ua:
        os_name = "Linux"
    else:
        os_name = "Other"

    return {"device_type": device_type, "browser": browser, "os": os_name}
