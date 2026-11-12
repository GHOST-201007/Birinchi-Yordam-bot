"""
test_start_menu_reset.py — /start eski shaxsiy menyu tugmasini fonda tozalaydi (MenuButtonDefault).

/start javobi hech qachon kechikmaydi va xatoda to'xtamaydi. Haqiqiy Telegram yoki bazaga murojaat qilinmaydi.
"""
import asyncio
import logging
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

from aiogram import types
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SetChatMenuButton

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("BOT_TOKEN", "123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567890")
os.environ.setdefault("GEMINI_API_KEY", "test_gemini_key")

import bot  # noqa: E402

USER_ID = 900000701
METHOD = SetChatMenuButton(chat_id=1, menu_button=types.MenuButtonDefault())
FREE_VIEW = bot.database.admin_premium_view(0, None, None)


class StartMenuResetTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        bot._menu_reset_done.clear()
        bot._menu_premium_done.clear()
        bot._premium_menu_cache.clear()
        # /start Premium holatini o'qiydi (admin_premium_view): haqiqiy bazaga murojaat qilinmasligi uchun
        patcher = mock.patch.object(bot.database, "get_premium_view", return_value=FREE_VIEW)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.menu_call = mock.AsyncMock(return_value=True)
        self.message = mock.MagicMock()
        self.message.text = "/start"
        self.message.from_user = SimpleNamespace(id=USER_ID, first_name="Ali", last_name=None, username="ali")
        self.message.answer = mock.AsyncMock()
        self.message.bot = SimpleNamespace(set_chat_menu_button=self.menu_call)
        self.state = mock.MagicMock()
        self.state.clear = mock.AsyncMock()

    async def start(self, text="/start"):
        self.message.text = text
        with mock.patch.object(bot.database, "register_user"):
            await bot.cmd_start(self.message, self.state)
        await self.drain()

    async def drain(self):
        """Fon vazifalari tugashini kutadi (testda)."""
        tasks = list(bot._menu_reset_tasks)
        if tasks:
            await asyncio.wait(tasks, timeout=2)

    async def test_start_sends_menu_button_default(self):
        await self.start()
        self.menu_call.assert_awaited_once()
        kwargs = self.menu_call.await_args.kwargs
        self.assertEqual(kwargs["chat_id"], USER_ID)
        self.assertIsInstance(kwargs["menu_button"], types.MenuButtonDefault)     # MenuButtonWebApp EMAS
        self.message.answer.assert_awaited()                                      # /start javob berdi

    async def test_every_start_variant_resets_including_deep_links(self):
        for i, text in enumerate(("/start", "/start ref_123", "/start wheel")):
            bot._menu_reset_done.clear()
            self.menu_call.reset_mock()
            with self.subTest(text=text):
                with mock.patch.object(bot.database, "get_user_info", return_value={"is_premium": 0}), \
                     mock.patch.object(bot, "get_web_app_url", new=mock.AsyncMock(return_value="https://x/app")), \
                     mock.patch.object(bot.database, "handle_referral", return_value=(False, 0, False)):
                    await self.start(text)
                self.menu_call.assert_awaited_once()

    async def test_telegram_error_does_not_break_start(self):
        self.menu_call.side_effect = TelegramForbiddenError(METHOD, "Forbidden: bot was blocked by the user")
        with self.assertLogs(level="WARNING") as logs:
            await self.start()
        self.message.answer.assert_awaited()                                      # /start baribir javob berdi
        joined = "\n".join(logs.output)
        self.assertIn("Shaxsiy menyu tugmasini tozalab bo'lmadi", joined)
        self.assertIn("TelegramForbiddenError", joined)

    async def test_slow_telegram_does_not_delay_start(self):
        # Deterministik: /start qaytganda fon vazifasi hali TUGAMAGAN (Telegram javob bermayapti), lekin javob berilgan
        gate = asyncio.Event()

        async def blocked(**kw):
            await gate.wait()

        self.menu_call.side_effect = blocked
        with mock.patch.object(bot, "MENU_RESET_TIMEOUT", 30.0), mock.patch.object(bot.database, "register_user"):
            await bot.cmd_start(self.message, self.state)
            pending = list(bot._menu_reset_tasks)
            self.message.answer.assert_awaited()
            self.assertEqual(len(pending), 1)
            self.assertFalse(pending[0].done(), "/start fon vazifasini kutib qolgan")
            gate.set()
            await self.drain()
        self.assertIn(USER_ID, bot._menu_reset_done)

    async def test_slow_telegram_times_out_with_warning(self):
        gate = asyncio.Event()

        async def blocked(**kw):
            await gate.wait()

        self.menu_call.side_effect = blocked
        with mock.patch.object(bot, "MENU_RESET_TIMEOUT", 0.05), self.assertLogs(level="WARNING") as logs:
            await self.start()
        self.message.answer.assert_awaited()
        self.assertIn("TimeoutError", " | ".join(logs.output))
        self.assertNotIn(USER_ID, bot._menu_reset_done)                           # muvaffaqiyatsiz: belgilanmaydi

    async def test_not_repeated_for_same_user_after_success(self):
        await self.start()
        await self.start()
        self.assertEqual(self.menu_call.await_count, 1)                           # jarayon ichida takroran yuborilmaydi

    async def test_failed_attempt_is_retried_on_next_start(self):
        self.menu_call.side_effect = [TelegramForbiddenError(METHOD, "Forbidden"), True]
        with self.assertLogs(level="WARNING"):
            await self.start()
        await self.start()
        self.assertEqual(self.menu_call.await_count, 2)
        self.assertIn(USER_ID, bot._menu_reset_done)

    async def test_no_exception_leaks_from_background_task(self):
        self.menu_call.side_effect = RuntimeError("boom " + "SECRET-TOKEN-MARKER")
        with self.assertLogs(level="WARNING") as logs:
            await self.start()
        self.assertNotIn("SECRET-TOKEN-MARKER", "\n".join(logs.output))          # xato matni emas, turi loglanadi
        self.assertEqual(len(bot._menu_reset_tasks), 0)                           # vazifa tozalandi


if __name__ == "__main__":
    unittest.main()
