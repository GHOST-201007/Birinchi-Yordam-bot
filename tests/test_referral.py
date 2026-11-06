"""
test_referral.py — P0-3: zonasiz registered_at bilan ham referal ball beradi.

Haqiqiy bazaga murojaat qilinmaydi: database._managed_cursor soxta kursor bilan almashtiriladi.
"""
import contextlib
import datetime
import os
import sys
import unittest
from unittest import mock

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("BOT_TOKEN", "123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567890")
os.environ.setdefault("GEMINI_API_KEY", "test_gemini_key")

import database  # noqa: E402

REFERRER = 900000301
NEW_USER = 900000302


class FakeCursor:
    """Faqat handle_referral ishlatadigan so'rovlarni taqlid qiladi."""

    def __init__(self, registered_at, referred_by=None, referral_count=1):
        self.registered_at = registered_at
        self.referred_by = referred_by
        self.referral_count = referral_count
        self.executed = []
        self._result = None

    def execute(self, sql, params=()):
        self.executed.append((sql, params))
        if sql.startswith("SELECT user_id FROM users"):
            self._result = (REFERRER,)
        elif sql.startswith("SELECT registered_at, referred_by"):
            self._result = (self.registered_at, self.referred_by)
        elif sql.startswith("SELECT COUNT(*)"):
            self._result = (self.referral_count,)
        else:
            self._result = None

    def fetchone(self):
        return self._result

    def score_updates(self):
        return [p for s, p in self.executed if "medicine_score" in s]


class HandleReferralTest(unittest.TestCase):
    def run_referral(self, cursor):
        conn = mock.MagicMock()

        @contextlib.contextmanager
        def fake_managed():
            yield conn, cursor

        with mock.patch.object(database, "_managed_cursor", fake_managed), \
             mock.patch.object(database, "check_and_grant_premium"):
            return database.handle_referral(NEW_USER, REFERRER)

    def naive_tashkent_now(self, seconds_ago=0):
        # PostgreSQL TIMESTAMP ustuni zonasiz Toshkent vaqtini qaytaradi
        return (database.get_uz_now() - datetime.timedelta(seconds=seconds_ago)).replace(tzinfo=None)

    def test_naive_registered_at_gives_10_points(self):
        cursor = FakeCursor(self.naive_tashkent_now(seconds_ago=1))
        result = self.run_referral(cursor)
        self.assertEqual(result, (True, 10, False))
        self.assertEqual(cursor.score_updates(), [(REFERRER,)])

    def test_iso_string_registered_at_works(self):
        cursor = FakeCursor(self.naive_tashkent_now(seconds_ago=5).isoformat())
        self.assertEqual(self.run_referral(cursor), (True, 10, False))

    def test_fifth_friend_gives_bonus(self):
        cursor = FakeCursor(self.naive_tashkent_now(seconds_ago=1), referral_count=5)
        self.assertEqual(self.run_referral(cursor), (True, 60, True))

    def test_old_user_gets_no_referral(self):
        cursor = FakeCursor(self.naive_tashkent_now(seconds_ago=3600))
        self.assertEqual(self.run_referral(cursor), (False, 0, False))
        self.assertEqual(cursor.score_updates(), [])

    def test_already_referred_user_gets_no_points(self):
        cursor = FakeCursor(self.naive_tashkent_now(seconds_ago=1), referred_by=123)
        self.assertEqual(self.run_referral(cursor), (False, 0, False))

    def test_bad_registered_at_is_logged_not_swallowed(self):
        cursor = FakeCursor("buzilgan-sana")
        with self.assertLogs(level="ERROR"):
            self.assertEqual(self.run_referral(cursor), (False, 0, False))

    def test_self_referral_rejected(self):
        self.assertEqual(database.handle_referral(REFERRER, REFERRER), (False, 0, False))


if __name__ == "__main__":
    unittest.main()
