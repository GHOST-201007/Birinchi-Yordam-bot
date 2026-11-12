"""
test_html_escape.py — P1-3: foydalanuvchi kiritgan qiymatlar parse_mode="HTML" matnida ekranlanadi.

Haqiqiy Telegram yoki bazaga murojaat qilinmaydi.
"""
import asyncio
import os
import sys
import unittest
from html.parser import HTMLParser
from types import SimpleNamespace
from unittest import mock

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("BOT_TOKEN", "123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567890")
os.environ.setdefault("GEMINI_API_KEY", "test_gemini_key")

import bot  # noqa: E402

EVIL = '<b>x</b><a href="http://e">'
TELEGRAM_TAGS = {"b", "i", "u", "s", "a", "code", "pre", "tg-spoiler", "blockquote"}


class TagCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def tags_in(text):
    p = TagCollector()
    p.feed(text)
    return p.tags


class HtmlEscapeTest(unittest.TestCase):
    def assert_safe(self, text):
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", text)
        for tag, attrs in tags_in(text):
            self.assertIn(tag, TELEGRAM_TAGS)
            self.assertNotEqual(attrs.get("href"), "http://e", "foydalanuvchi havolasi HTML ga tushib qoldi")

    def test_admin_premium_panel(self):
        # Yangi panel (eski _build_premium_list_text o'rniga): user kartasi, tasdiqlash va natija matnlari
        user = {"user_id": 1, "full_name": EVIL, "username": "user", "active": False, "tier": "free",
                "unlimited": False, "expires": None, "score": 0}
        self.assert_safe(bot._pm_card_view(user, 0)[0])
        self.assert_safe(bot._pm_tier_view(user, 0)[0])
        self.assert_safe(bot._pm_confirm_view(user, 0, "pro", "7", "n", 0)[0])
        self.assert_safe(bot._pm_remove_confirm_view(user, 0, "n")[0])
        result = {"tier": "pro", "kept_higher": False, "unlimited": True, "expires": None}
        self.assert_safe(bot._pm_grant_result_text(user, result, None, "s", None))
        self.assert_safe(bot._pm_remove_result_text(user, "s", None))
        evil_username = dict(user, full_name="Ali", username=EVIL)
        self.assert_safe(bot._pm_card_view(evil_username, 0)[0])

    def test_admin_ban_list(self):
        rows = [(1, 0, None, EVIL, "user")]
        self.assert_safe(bot._build_ban_list_text(rows, 1, 0))

    def test_medical_profile(self):
        msg = mock.MagicMock()
        msg.from_user = SimpleNamespace(id=1)
        msg.answer = mock.AsyncMock()
        profile = (EVIL, 30, 70, 175, EVIL, EVIL)
        with mock.patch.object(bot.database, "get_medical_profile", return_value=profile):
            asyncio.run(bot.medical_profile_menu(msg))
        text = msg.answer.await_args.args[0]
        self.assert_safe(text)
        self.assertEqual(text.count("&lt;b&gt;x&lt;/b&gt;"), 3)

    def test_reminder_saved_message(self):
        callback = mock.MagicMock()
        callback.data = "rem_days_daily"
        callback.from_user = SimpleNamespace(id=1)
        callback.message.edit_text = mock.AsyncMock()
        callback.answer = mock.AsyncMock()
        state = mock.MagicMock()
        state.get_data = mock.AsyncMock(return_value={"medicine_name": EVIL, "times_str": "08:00"})
        state.clear = mock.AsyncMock()
        with mock.patch.object(bot.database, "add_reminder", return_value=1):
            asyncio.run(bot.reminder_days_chosen(callback, state))
        self.assert_safe(callback.message.edit_text.await_args.args[0])


if __name__ == "__main__":
    unittest.main()
