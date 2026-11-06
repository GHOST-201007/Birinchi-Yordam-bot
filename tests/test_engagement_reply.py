"""
test_engagement_reply.py — P0-2: engagement yuborilgan kuni oddiy matn AI ga ketadi,
faqat engagement xabariga reply javob deb qabul qilinadi.

Haqiqiy Telegram, Gemini yoki bazaga murojaat qilinmaydi.
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
from services import engagement  # noqa: E402

USER_ID = 900000201
ENGAGEMENT_MSG_ID = 555
TODAY = "2026-11-06"


def make_message(text, reply_to=None):
    msg = mock.MagicMock()
    msg.text = text
    msg.from_user = SimpleNamespace(id=USER_ID)
    msg.chat = SimpleNamespace(id=USER_ID)
    msg.reply_to_message = reply_to
    msg.reply = mock.AsyncMock()
    msg.answer = mock.AsyncMock()
    return msg


def bot_message(message_id):
    return SimpleNamespace(message_id=message_id, from_user=SimpleNamespace(id=1, is_bot=True))


class FallbackTextEngagementTest(unittest.TestCase):
    def setUp(self):
        self.state = mock.MagicMock()
        self.state.get_state = mock.AsyncMock(return_value=None)
        self.state.set_state = mock.AsyncMock()

        # Bugun 08:00 savoli yuborilgan va javob berilmagan: faqat ENGAGEMENT_MSG_ID ga reply mos keladi
        def find(user_id, message_id):
            if user_id == USER_ID and message_id == ENGAGEMENT_MSG_ID:
                return ("08:00", TODAY)
            return None

        self.find = mock.MagicMock(side_effect=find)
        self.update = mock.MagicMock()
        self.ai = mock.AsyncMock()
        self.patches = [
            mock.patch.object(engagement, "find_unanswered_by_reply", self.find),
            mock.patch.object(engagement, "update_engagement_answer", self.update),
            mock.patch.object(bot, "handle_ai_chat", self.ai),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()

    def run_handler(self, msg):
        asyncio.run(bot.fallback_text(msg, self.state))

    def test_plain_text_goes_to_ai(self):
        msg = make_message("bolam zaharlandi")
        self.run_handler(msg)
        self.ai.assert_awaited_once()
        self.update.assert_not_called()
        msg.reply.assert_not_called()

    def test_reply_to_other_bot_message_goes_to_ai(self):
        msg = make_message("bolam zaharlandi", reply_to=bot_message(999))
        self.run_handler(msg)
        self.ai.assert_awaited_once()
        self.update.assert_not_called()

    def test_reply_to_engagement_is_accepted(self):
        msg = make_message("Yaxshi uxladim", reply_to=bot_message(ENGAGEMENT_MSG_ID))
        self.run_handler(msg)
        self.ai.assert_not_awaited()
        self.update.assert_called_once_with(USER_ID, "08:00", TODAY, "Yaxshi uxladim")
        msg.reply.assert_awaited_once()
        self.assertIn("Javobingiz qabul qilindi", msg.reply.await_args.args[0])

    def test_premium_reply_is_html_escaped(self):
        self.find.side_effect = lambda u, m: ("premium_checkin", TODAY)
        msg = make_message("Charchadim", reply_to=bot_message(ENGAGEMENT_MSG_ID))
        with mock.patch.object(engagement, "generate_premium_reply",
                               new=mock.AsyncMock(return_value="**Dam oling** <3")):
            self.run_handler(msg)
        sent = msg.reply.await_args.args[0]
        self.assertEqual(sent, "<b>Dam oling</b> &lt;3")

    def test_premium_reply_fallback_when_ai_returns_none(self):
        result = asyncio.run(engagement.generate_premium_reply("x", mock.AsyncMock(return_value=None)))
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
