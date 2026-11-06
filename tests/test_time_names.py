"""
test_time_names.py — P2-2: bot.py da `time` — modul, `dtime` — datetime.time sinfi.
"""
import datetime
import os
import sys
import time
import unittest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("BOT_TOKEN", "123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567890")
os.environ.setdefault("GEMINI_API_KEY", "test_gemini_key")

import bot  # noqa: E402


class TimeNamesTest(unittest.TestCase):
    def test_time_is_module(self):
        self.assertIs(bot.time, time)
        self.assertTrue(callable(bot.time.time))

    def test_dtime_is_datetime_time(self):
        self.assertIs(bot.dtime, datetime.time)


if __name__ == "__main__":
    unittest.main()
