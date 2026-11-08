"""
test_free_ai_limit.py — bepul foydalanuvchiga JAMI 1 ta AI savol (bir martalik), kunlik limit yo'q.
Bot va mini app bitta kvotani ulashadi; limit tugaganda botda Premium taklifi (premium_upsell, tugma bilan).
Pro / Plus / Ultra limitlari (15 / 30 / 100) o'zgarmagan.
"""
import inspect
import os
import sys
import unittest
from unittest import mock

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("BOT_TOKEN", "123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567890")
os.environ.setdefault("GEMINI_API_KEY", "test_gemini_key")

import bot  # noqa: E402
import database  # noqa: E402


class FreeLimitSourceTest(unittest.TestCase):
    def test_free_tier_has_no_daily_allowance(self):
        src = inspect.getsource(database.try_consume_daily_request)
        self.assertNotIn("FREE_AI_DAILY_LIMIT", src)
        self.assertIn("max_requests = 0", src)
        for tier, default in (("PRO", "15"), ("PLUS", "30"), ("ULTRA", "100")):
            self.assertIn(f'os.environ.get("{tier}_AI_DAILY_LIMIT", "{default}")', src)    # premium limitlar o'zgarmagan

    def test_bot_has_no_try_tomorrow_message(self):
        with open(os.path.join(PROJECT_DIR, "bot.py"), encoding="utf-8") as f:
            self.assertNotIn("ertaga urining", f.read())          # bepul uchun "ertaga" yo'q — Premium taklifi


class BotLimitOfferTest(unittest.IsolatedAsyncioTestCase):
    async def test_disease_callback_limit_shows_premium_offer(self):
        callback = mock.MagicMock()
        callback.data = "dis_1_0"
        callback.from_user.id = 424242
        callback.answer = mock.AsyncMock()
        callback.message.edit_text = mock.AsyncMock()
        upsell = mock.AsyncMock()
        with mock.patch.object(bot.database, "try_consume_free_ai", return_value=False), \
                mock.patch.object(bot.database, "try_consume_daily_request", return_value=False), \
                mock.patch.object(bot, "premium_upsell", upsell), \
                mock.patch.object(bot, "get_gemini_response", mock.AsyncMock()) as ai:
            await bot.process_disease_callback(callback)
        upsell.assert_awaited_once_with(callback)
        ai.assert_not_called()

    async def test_premium_upsell_has_premium_button(self):
        message = mock.MagicMock(spec=bot.types.Message)
        message.answer = mock.AsyncMock()
        await bot.premium_upsell(message)
        kwargs = message.answer.call_args.kwargs
        self.assertIn("Premium", message.answer.call_args.args[0])
        self.assertIsNotNone(kwargs.get("reply_markup"))

    def test_deep_link_consult_uses_premium_upsell(self):
        src = inspect.getsource(bot.cmd_start)
        block = src[src.index("ai_consult_"):]
        self.assertIn("await premium_upsell(message)", block)


if __name__ == "__main__":
    unittest.main()
