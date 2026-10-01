import re

# نفس قواعد normalizeArabic() في واجهة المكتبة (library.html) — أي تعديل هنا يُعدَّل هناك
_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_TRANSLATE = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ة": "ه",
    "ى": "ي", "ئ": "ي",
    "ؤ": "و",
})
_SPACES = re.compile(r"\s+")


def normalize_ar(text):
    """تطبيع للبحث: الهمزات على الألف ← ا، ة ← ه، ى/ئ ← ي، ؤ ← و، وحذف التشكيل والتطويل.
    فيجد "لغز القطار الأزرق" عند كتابة "الازرق"، و"ثلاثة عشر لغزاً" عند كتابة "ثلاثه عشر لغزا"."""
    if not text:
        return ""
    text = _DIACRITICS.sub("", str(text)).translate(_TRANSLATE).lower()
    return _SPACES.sub(" ", text).strip()
