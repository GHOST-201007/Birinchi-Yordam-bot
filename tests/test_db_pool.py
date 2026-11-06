"""
test_db_pool.py — P2-1: ulanish pooli kichik (minconn=2, maxconn=10).
Haqiqiy bazaga ulanilmaydi: ThreadedConnectionPool mock qilinadi.
"""
import os
import sys
import unittest
from unittest import mock

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import database  # noqa: E402


class DbPoolTest(unittest.TestCase):
    def test_pool_limits(self):
        fake_pool_cls = mock.MagicMock()
        with mock.patch.object(database, "db_pool", None), \
             mock.patch.object(database, "ThreadedConnectionPool", fake_pool_cls):
            database.get_connection()
        kwargs = fake_pool_cls.call_args.kwargs
        self.assertEqual(kwargs["minconn"], 2)
        self.assertEqual(kwargs["maxconn"], 10)


if __name__ == "__main__":
    unittest.main()
