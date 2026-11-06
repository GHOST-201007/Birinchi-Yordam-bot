"""
test_throttling_cleanup.py — P2-9: ThrottlingMiddleware lug'atlari cheksiz o'smaydi.
"""
import asyncio
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("BOT_TOKEN", "123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567890")
os.environ.setdefault("GEMINI_API_KEY", "test_gemini_key")

import bot  # noqa: E402


class ThrottlingCleanupTest(unittest.TestCase):
    def run_requests(self, mw, user_ids, now):
        handler = mock.AsyncMock(return_value="ok")

        async def go():
            for uid in user_ids:
                await mw(handler, object(), {"event_from_user": SimpleNamespace(id=uid)})

        with mock.patch.object(bot.time, "time", return_value=now):
            asyncio.run(go())
        return handler

    def test_old_entries_removed(self):
        mw = bot.ThrottlingMiddleware()
        mw.CLEANUP_EVERY = 100
        # 99 ta eski foydalanuvchi (t=10), keyin 1 ta yangi (t=1000) → tozalash ishga tushadi
        self.run_requests(mw, range(1, 100), now=10.0)
        mw.last_warnings[5] = 10.0
        self.assertEqual(len(mw.last_requests), 99)
        self.run_requests(mw, [1000], now=1000.0)
        self.assertEqual(list(mw.last_requests), [1000])
        self.assertEqual(mw.last_warnings, {})

    def test_recent_entries_kept(self):
        mw = bot.ThrottlingMiddleware()
        mw.CLEANUP_EVERY = 10
        self.run_requests(mw, range(1, 10), now=100.0)
        self.run_requests(mw, [10], now=110.0)  # 10 s o'tdi — STALE_AFTER (60 s) dan kam
        self.assertEqual(len(mw.last_requests), 10)

    def test_throttling_still_works(self):
        mw = bot.ThrottlingMiddleware()
        handler = self.run_requests(mw, [1], now=50.0)
        handler.assert_awaited_once()
        handler2 = self.run_requests(mw, [1], now=50.5)  # 1 s dan tez — bloklanadi
        handler2.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
