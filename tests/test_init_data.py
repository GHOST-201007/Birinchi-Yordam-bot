"""
test_init_data.py — bot.parse_init_data: Telegram WebApp initData tekshiruvi.

initData testda Telegram hujjatidagi algoritm bo'yicha mustaqil imzolanadi
(HMAC-SHA256, secret = HMAC("WebAppData", token)). Tarmoq yoki bazaga murojaat yo'q.
"""
import hashlib
import hmac
import json
import os
import sys
import unittest
import urllib.parse
from unittest import mock

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("BOT_TOKEN", "123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567890")
os.environ.setdefault("GEMINI_API_KEY", "test_gemini_key")

import bot  # noqa: E402

TOKEN = "111222333:TEST-token-for-init-data-0123456789"
NOW = 1_800_000_000
USER = {"id": 424242, "first_name": "Ali", "username": "ali_test"}


def sign(fields: dict, token: str = TOKEN) -> str:
    """Telegram hujjatiga ko'ra imzolangan initData qatorini yasaydi."""
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urllib.parse.urlencode({**fields, "hash": digest})


def make(auth_date=NOW, user=USER, token=TOKEN, extra=None) -> str:
    fields = {"auth_date": str(auth_date), "query_id": "AAH-test"}
    if user is not None:
        fields["user"] = json.dumps(user, separators=(",", ":"))
    fields.update(extra or {})
    return sign(fields, token)


class ParseInitDataTest(unittest.TestCase):
    def parse(self, init_data, **kw):
        return bot.parse_init_data(init_data, bot_token=kw.pop("bot_token", TOKEN), now=kw.pop("now", NOW), **kw)

    def test_valid_returns_user(self):
        user = self.parse(make())
        self.assertEqual(user["id"], 424242)
        self.assertEqual(user["first_name"], "Ali")

    def test_unicode_name_valid(self):
        user = self.parse(make(user={"id": 7, "first_name": "Yusuf — Али"}))
        self.assertEqual(user["id"], 7)

    def test_tampered_hash_rejected(self):
        init = make()
        bad = init[:-1] + ("0" if init[-1] != "0" else "1")
        self.assertIsNone(self.parse(bad))

    def test_tampered_field_rejected(self):
        init = make()
        forged = init.replace("424242", "999999")
        self.assertNotEqual(init, forged)
        self.assertIsNone(self.parse(forged))

    def test_wrong_bot_token_rejected(self):
        self.assertIsNone(self.parse(make(token="999:OTHER-token")))

    def test_missing_hash_rejected(self):
        fields = {"auth_date": str(NOW), "user": json.dumps(USER)}
        self.assertIsNone(self.parse(urllib.parse.urlencode(fields)))

    def test_auth_date_25_hours_old_rejected(self):
        self.assertIsNone(self.parse(make(auth_date=NOW - 25 * 3600)))

    def test_auth_date_23_hours_old_accepted(self):
        self.assertIsNotNone(self.parse(make(auth_date=NOW - 23 * 3600)))

    def test_auth_date_in_future_5_minutes_rejected(self):
        self.assertIsNone(self.parse(make(auth_date=NOW + 300)))

    def test_small_clock_skew_accepted(self):
        self.assertIsNotNone(self.parse(make(auth_date=NOW + 30)))

    def test_missing_or_bad_auth_date_rejected(self):
        self.assertIsNone(self.parse(sign({"user": json.dumps(USER)})))
        self.assertIsNone(self.parse(sign({"auth_date": "abc", "user": json.dumps(USER)})))

    def test_missing_user_rejected(self):
        self.assertIsNone(self.parse(make(user=None)))

    def test_bad_user_payloads_rejected(self):
        for payload in ("not json", "[]", "123", '{"first_name":"x"}', '{"id":"5"}',
                        '{"id":true}', '{"id":0}', '{"id":-5}', '{"id":1.5}'):
            with self.subTest(user=payload):
                self.assertIsNone(self.parse(sign({"auth_date": str(NOW), "user": payload})))

    def test_duplicate_keys_rejected(self):
        init = make() + "&auth_date=" + str(NOW)
        self.assertIsNone(self.parse(init))

    def test_empty_and_wrong_types_rejected(self):
        for value in ("", None, 123, b"x", [], "garbage", "a=b", "hash=abc"):
            with self.subTest(value=value):
                self.assertIsNone(self.parse(value))

    def test_no_bot_token_returns_none(self):
        with mock.patch.object(bot, "TOKEN", ""):
            self.assertIsNone(bot.parse_init_data(make(), now=NOW))
        self.assertIsNone(bot.parse_init_data(make(), bot_token="", now=NOW))

    def test_defaults_to_module_token_and_real_clock(self):
        import time as _time
        with mock.patch.object(bot, "TOKEN", TOKEN):
            fresh = make(auth_date=int(_time.time()))
            self.assertEqual(bot.parse_init_data(fresh)["id"], 424242)

    def test_never_raises_and_does_not_log_init_data(self):
        secret_marker = "SUPER-SECRET-MARKER-123"
        with self.assertNoLogs(level="DEBUG"):
            for value in (make(), "%%%", secret_marker, make(user={"id": 1, "first_name": secret_marker})):
                bot.parse_init_data(value, bot_token=TOKEN, now=NOW)


if __name__ == "__main__":
    unittest.main()
