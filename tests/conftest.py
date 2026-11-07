"""
pytest sozlamalari.

test_ban_cache_local.py faqat toza, ALOHIDA jarayonda ishlashi kerak (psycopg2/dotenv soxta modullar bilan
almashtiriladi, tarmoq bloklanadi). Umumiy `pytest tests` jarayonida u izolyatsiyasiz yuklanadi va 38 ta
test `'NoneType' object has no attribute 'get_connection'` bilan yiqiladi.

Shuning uchun:
  * umumiy yig'ishda bu fayl chiqarib tashlanadi (collect_ignore); uning o'rniga tests/test_ban_cache_isolated.py
    bitta test sifatida butun to'plamni BY_BAN_CACHE_ISOLATED=1 bilan subprocess'da yurgizadi;
  * fayl pytest'ga aniq yo'l bilan berilsa (collect_ignore bunda ishlamaydi) faqat shu subprocess runner qoladi.
`python -m unittest tests.test_ban_cache_local` va `BY_BAN_CACHE_ISOLATED=1 pytest tests/test_ban_cache_local.py`
avvalgidek ishlaydi (bayroq o'rnatilgan bo'lsa hech narsa chiqarilmaydi).
"""
import os

_FLAG = "BY_BAN_CACHE_ISOLATED"
_FILE = "test_ban_cache_local.py"
_RUNNER_CLASS = "TestBanCacheIsolatedProcess"

collect_ignore = [] if os.environ.get(_FLAG) == "1" else [_FILE]


def pytest_collection_modifyitems(config, items):
    if os.environ.get(_FLAG) == "1":
        return
    kept, dropped = [], []
    for item in items:
        in_ban_file = os.path.basename(str(item.fspath)) == _FILE
        cls_name = getattr(getattr(item, "cls", None), "__name__", None)
        (dropped if in_ban_file and cls_name != _RUNNER_CLASS else kept).append(item)
    if dropped:
        items[:] = kept
        config.hook.pytest_deselected(items=dropped)
