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

    def test_free_ai_daily_limit_env_not_read_anywhere(self):
        # Eski FREE_AI_DAILY_LIMIT o'zgaruvchisi kodda o'qilmaydi (serverdagi .env da qolgan bo'lsa — ta'sirsiz)
        skip = {"venv", ".venv", ".git", "tests", "__pycache__", "node_modules"}
        for dirpath, dirs, files in os.walk(PROJECT_DIR):
            dirs[:] = [d for d in dirs if d not in skip]
            for name in files:
                if name.endswith(".py"):
                    with open(os.path.join(dirpath, name), encoding="utf-8", errors="ignore") as f:
                        self.assertNotIn("FREE_AI_DAILY_LIMIT", f.read(), os.path.join(dirpath, name))

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
                mock.patch.object(bot.database, "try_consume_spin_ai_bonus", return_value=False), \
                mock.patch.object(bot, "premium_upsell", upsell), \
                mock.patch.object(bot, "get_gemini_response", mock.AsyncMock()) as ai:
            await bot.process_disease_callback(callback)
        upsell.assert_awaited_once_with(callback)
        ai.assert_not_called()

    async def upsell(self, premium_info):
        message = mock.MagicMock(spec=bot.types.Message)
        message.from_user = mock.MagicMock(id=424242)
        message.answer = mock.AsyncMock()
        with mock.patch.object(bot.database, "get_premium_info", return_value=premium_info) as info, \
                mock.patch.dict("os.environ", {}, clear=False):
            for k in ("PRO_AI_DAILY_LIMIT", "PLUS_AI_DAILY_LIMIT", "ULTRA_AI_DAILY_LIMIT"):
                os.environ.pop(k, None)
            await bot.premium_upsell(message)
        info.assert_called_once_with(424242)
        return message.answer.call_args.args[0], message.answer.call_args.kwargs

    async def test_premium_upsell_has_premium_button(self):
        text, kwargs = await self.upsell((False, None, "free"))
        self.assertIn("Premium", text)
        self.assertIn("Bepul AI so'rovlar limiti tugadi", text)
        self.assertIsNotNone(kwargs.get("reply_markup"))

    async def test_free_upsell_lists_tier_limits_not_unlimited(self):
        text, _ = await self.upsell((False, None, "free"))
        self.assertNotIn("cheksiz", text.lower())
        for line in ("Pro — kuniga 15 ta", "Plus — kuniga 30 ta", "Ultra — kuniga 100 ta"):
            self.assertIn(line, text)

    async def test_premium_user_sees_daily_limit_not_free_message(self):
        for tier, limit, higher in (("pro", 15, "Plus — kuniga 30 ta"), ("plus", 30, "Ultra — kuniga 100 ta")):
            with self.subTest(tier=tier):
                text, kwargs = await self.upsell((True, None, tier))
                self.assertNotIn("Bepul", text)
                self.assertNotIn("cheksiz", text.lower())
                self.assertIn(f"kuniga {limit} ta AI so'rov", text)
                self.assertIn("ertaga soat 00:00", text)
                self.assertIn(higher, text)
                self.assertIsNotNone(kwargs.get("reply_markup"))          # yuqoriroq tarif — tugma bor

    async def test_ultra_user_no_upgrade_button(self):
        for info in ((True, None, "ultra"), (True, None, "free")):         # muddatsiz premium — Ultra
            with self.subTest(info=info):
                text, kwargs = await self.upsell(info)
                self.assertIn("kuniga 100 ta AI so'rov", text)
                self.assertNotIn("Bepul", text)
                self.assertIsNone(kwargs.get("reply_markup"))

    async def test_callback_variant_edits_message(self):
        callback = mock.MagicMock()
        callback.from_user.id = 424242
        callback.message.edit_text = mock.AsyncMock()
        with mock.patch.object(bot.database, "get_premium_info", return_value=(True, None, "pro")):
            await bot.premium_upsell(callback)
        self.assertIn("Premium Pro", callback.message.edit_text.call_args.args[0])

    def test_no_unlimited_word_in_bot_ai_texts(self):
        src = inspect.getsource(bot.premium_upsell_text)
        self.assertNotIn("cheksiz", src.lower())

    def test_deep_link_consult_uses_premium_upsell(self):
        src = inspect.getsource(bot.cmd_start)
        block = src[src.index("ai_consult_"):]
        self.assertIn("await premium_upsell(message)", block)


if __name__ == "__main__":
    unittest.main()
