import os
from functools import lru_cache

from PIL import Image

STATIC_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static')


@lru_cache(maxsize=512)
def _read_size(full_path, mtime):
    with Image.open(full_path) as image:
        return image.size


def static_image_size(rel_path):
    """(عرض، ارتفاع) لصورة داخل static — لوسوم og:image:width/height وأبعاد <img> (تمنع CLS).
    يقرأ ترويسة الصورة فقط، مع كاش حسب وقت التعديل. None لو الملف غير موجود أو غير صالح."""
    if not rel_path:
        return None
    full_path = os.path.realpath(os.path.join(STATIC_ROOT, rel_path))
    if not full_path.startswith(os.path.realpath(STATIC_ROOT)):
        return None
    try:
        return _read_size(full_path, os.path.getmtime(full_path))
    except (OSError, ValueError):
        return None
