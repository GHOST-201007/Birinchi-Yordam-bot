"""
test_ban_cache_isolated.py — pytest uchun kirish nuqtasi.

test_ban_cache_local.py (45 ta test) umumiy pytest jarayonida yurmaydi (tests/conftest.py uni yig'ishdan chiqaradi),
chunki u toza jarayonni talab qiladi. Bu yerda uning tayyor runner'i (TestBanCacheIsolatedProcess) ulanadi:
u butun to'plamni `BY_BAN_CACHE_ISOLATED=1` bilan subprocess'da yurgizadi va returncode != 0 bo'lsa yiqiladi.
Mantiq bitta joyda (test_ban_cache_local.py) qoladi, takrorlanmaydi.
"""
import unittest

from tests.test_ban_cache_local import TestBanCacheIsolatedProcess  # noqa: F401  (pytest shu sinfni yig'adi)


def load_tests(loader, standard_tests, pattern):
    # `python -m unittest` da test_ban_cache_local.py o'zining load_tests() bilan shu runner'ni yurgizadi:
    # bu fayl ikkinchi marta yurgizmasin.
    return unittest.TestSuite()
