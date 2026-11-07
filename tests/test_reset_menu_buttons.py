"""
test_reset_menu_buttons.py — scripts/reset_menu_buttons.py (bir martalik: shaxsiy menyu tugmalarini o'chirish).

Telegram va baza MOCK qilinadi. Tezlik cheklovi virtual soat bilan tekshiriladi (haqiqiy kutish yo'q).
"""
import asyncio
import io
import logging
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

from aiogram import types
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramNotFound,
    TelegramRetryAfter,
    TelegramUnauthorizedError,
)
from aiogram.methods import SetChatMenuButton

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_DIR, "scripts"))

import reset_menu_buttons as rmb  # noqa: E402

METHOD = SetChatMenuButton(chat_id=1, menu_button=types.MenuButtonDefault())
TOKEN_MARKER = "SECRET-BOT-TOKEN-123456:AAH-marker"
DB_MARKER = "postgresql://user:SECRET-DB-PASSWORD@db.internal/prod"


class VClock:
    """Virtual soat: sleep() haqiqatda kutmaydi, vaqtni suradi."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    async def sleep(self, seconds):
        target = self.now + seconds
        await asyncio.sleep(0)
        self.now = max(self.now, target)


class FakeBot:
    def __init__(self, clock, behavior=None):
        self.clock = clock
        self.behavior = behavior or {}      # uid -> [istisno | None, ...] yoki callable(urinish_raqami) -> istisno | None
        self.calls = []                     # (vaqt, chat_id, menu_button)
        self.attempts = {}
        self.session = SimpleNamespace(close=mock.AsyncMock())

    async def set_chat_menu_button(self, chat_id, menu_button):
        self.calls.append((self.clock(), chat_id, menu_button))
        n = self.attempts[chat_id] = self.attempts.get(chat_id, 0) + 1
        script = self.behavior.get(chat_id)
        outcome = None
        if callable(script):
            outcome = script(n)
        elif script:
            outcome = script.pop(0)
        if outcome is not None:
            raise outcome
        return True

    def times(self):
        return [c[0] for c in self.calls]


def retry_after(seconds):
    return TelegramRetryAfter(method=METHOD, message="Too Many Requests", retry_after=seconds)


async def run(bot, ids, clock, **kw):
    return await rmb.reset_menu_buttons(bot, ids, clock=clock, sleep=clock.sleep, **kw)


class ResetCoreTest(unittest.IsolatedAsyncioTestCase):
    async def test_every_user_gets_default_menu_button(self):
        clock = VClock()
        bot = FakeBot(clock)
        result = await run(bot, list(range(1, 46)), clock)
        self.assertEqual((result.total, result.success, result.skipped), (45, 45, 0))
        self.assertEqual(sorted(c[1] for c in bot.calls), list(range(1, 46)))     # har biriga bittadan
        for _, _, button in bot.calls:
            self.assertIsInstance(button, types.MenuButtonDefault)                # MenuButtonWebApp EMAS

    async def test_rate_never_exceeds_20_per_second(self):
        clock = VClock()
        bot = FakeBot(clock)
        await run(bot, list(range(1, 201)), clock)
        t = sorted(bot.times())
        self.assertEqual(len(t), 200)
        for i in range(len(t) - 20):
            self.assertGreaterEqual(t[i + 20] - t[i], 0.999, f"{i}-so'rovdan boshlab 1 soniyada 20 tadan ko'p")
        self.assertGreaterEqual(t[-1] - t[0], 9.9)          # 200 so'rov >= ~10 soniya

    async def test_blocked_and_chat_not_found_are_skipped_not_fatal(self):
        clock = VClock()
        bot = FakeBot(clock, {
            2: [TelegramForbiddenError(METHOD, "Forbidden: bot was blocked by the user")],
            3: [TelegramBadRequest(METHOD, "Bad Request: chat not found")],
            4: [TelegramNotFound(METHOD, "Not Found")],
            5: [TelegramBadRequest(METHOD, "Bad Request: something else")],
            6: [TelegramForbiddenError(METHOD, "Forbidden: user is deactivated")],
        })
        result = await run(bot, list(range(1, 11)), clock)
        self.assertEqual((result.total, result.success, result.skipped), (10, 5, 5))
        self.assertEqual(result.reasons[rmb.R_FORBIDDEN], 2)
        self.assertEqual(result.reasons[rmb.R_NOT_FOUND], 2)
        self.assertEqual(result.reasons[rmb.R_BAD_REQUEST], 1)
        self.assertEqual(bot.attempts[2], 1)                # bloklaganga qayta urinilmaydi

    async def test_unexpected_error_for_one_user_does_not_stop_the_rest(self):
        clock = VClock()
        bot = FakeBot(clock, {3: [RuntimeError("boom")]})
        result = await run(bot, [1, 2, 3, 4, 5], clock)
        self.assertEqual((result.success, result.skipped), (4, 1))
        self.assertEqual(result.reasons[rmb.R_UNEXPECTED], 1)

    async def test_retry_after_waits_for_everyone_then_retries(self):
        clock = VClock()
        bot = FakeBot(clock, {10: [retry_after(3)]})
        result = await run(bot, list(range(1, 31)), clock)
        self.assertEqual((result.success, result.skipped), (30, 0))
        self.assertEqual(bot.attempts[10], 2)               # qayta urinildi
        fail_time = bot.calls[[c[1] for c in bot.calls].index(10)][0]
        retry_time = [c[0] for c in bot.calls if c[1] == 10][1]
        self.assertGreaterEqual(retry_time - fail_time, 3.0)
        # RetryAfter oynasida (>= 3 s) HECH QAYSI so'rov yuborilmagan: hamma kutgan
        others = [t for t in bot.times() if fail_time < t < fail_time + 3.0]
        self.assertEqual(others, [])

    async def test_retry_after_exhausted_is_skipped_with_bounded_attempts(self):
        clock = VClock()
        bot = FakeBot(clock, {7: lambda n: retry_after(1)})
        result = await run(bot, [6, 7, 8], clock, max_retries=2)
        self.assertEqual((result.success, result.skipped), (2, 1))
        self.assertEqual(result.reasons[rmb.R_RETRY_AFTER], 1)
        self.assertEqual(bot.attempts[7], 3)                # 1 + 2 qayta urinish, cheksiz emas

    async def test_transient_network_error_is_retried(self):
        clock = VClock()
        bot = FakeBot(clock, {2: [TelegramNetworkError(METHOD, f"HTTP Client says - {TOKEN_MARKER}")]})
        result = await run(bot, [1, 2, 3], clock)
        self.assertEqual((result.success, result.skipped), (3, 0))
        self.assertEqual(bot.attempts[2], 2)

    async def test_persistent_network_error_skipped_and_reason_has_no_message(self):
        clock = VClock()
        bot = FakeBot(clock, {2: lambda n: TelegramNetworkError(METHOD, f"url=https://api.telegram.org/bot{TOKEN_MARKER}/x")})
        result = await run(bot, [1, 2], clock, max_retries=2)
        self.assertEqual(result.reasons[rmb.R_NETWORK], 1)
        self.assertNotIn(TOKEN_MARKER, rmb.format_summary(result))

    async def test_invalid_token_aborts_immediately(self):
        clock = VClock()
        bot = FakeBot(clock, {1: [TelegramUnauthorizedError(METHOD, "Unauthorized")]})
        with self.assertRaises(rmb.FatalError):
            await run(bot, list(range(1, 101)), clock)
        self.assertLess(len(bot.calls), 100)                # qolganlariga so'rov yuborilmagan

    async def test_dry_run_sends_nothing(self):
        clock = VClock()
        bot = FakeBot(clock)
        result = await run(bot, [1, 2, 3], clock, dry_run=True)
        self.assertEqual(bot.calls, [])
        self.assertEqual((result.total, result.success, result.skipped, result.dry_run), (3, 0, 0, True))

    async def test_progress_reported_every_100(self):
        clock = VClock()
        seen = []
        await run(FakeBot(clock), list(range(1, 251)), clock, progress=lambda done, total: seen.append((done, total)))
        self.assertEqual(seen, [(100, 250), (200, 250)])


class ResetMainTest(unittest.TestCase):
    ENV = {"BOT_TOKEN": TOKEN_MARKER, "DATABASE_URL": DB_MARKER}

    def run_main(self, argv=(), env=None, ids=(1, 2, 3), bot=None, fetch=None):
        out = io.StringIO()
        fetch_mock = mock.MagicMock(side_effect=fetch) if fetch else mock.MagicMock(return_value=list(ids))
        factory = mock.MagicMock(return_value=bot)
        records = []

        class Collect(logging.Handler):
            def emit(self, record):
                records.append(record)

        handler, root = Collect(level=logging.DEBUG), logging.getLogger()
        old_level = root.level
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)
        try:
            code = rmb.main(list(argv), env=self.ENV if env is None else env,
                            fetch_user_ids=fetch_mock, bot_factory=factory, stdout=out)
        finally:
            root.removeHandler(handler)
            root.setLevel(old_level)
        # Skript o'zi hech narsa loglamaydi (asyncio'ning ichki DEBUG xabari hisobga olinmaydi), sirlar loglarda yo'q
        own = [r for r in records if r.name != "asyncio"]
        self.assertEqual(own, [], [r.getMessage() for r in own])
        for r in records:
            for secret in (TOKEN_MARKER, "SECRET-DB-PASSWORD"):
                self.assertNotIn(secret, r.getMessage())
        return code, out.getvalue(), fetch_mock, factory

    def real_bot(self, behavior=None):
        return FakeBot(lambda: 0.0, behavior)

    def test_summary_total_success_skipped(self):
        bot = self.real_bot({2: [TelegramForbiddenError(METHOD, "Forbidden: bot was blocked by the user")],
                             4: [TelegramBadRequest(METHOD, "Bad Request: chat not found")]})
        code, out, _, factory = self.run_main(ids=[1, 2, 3, 4, 5], bot=bot)
        self.assertEqual(code, 0)
        self.assertIn("Jami: 5", out)
        self.assertIn("Muvaffaqiyatli: 3", out)
        self.assertIn("O'tkazib yuborilgan: 2", out)
        factory.assert_called_once_with(TOKEN_MARKER)
        bot.session.close.assert_awaited_once()             # sessiya yopiladi

    def test_dry_run_counts_only_and_creates_no_bot_needs_no_token(self):
        code, out, fetch, factory = self.run_main(["--dry-run"], env={"DATABASE_URL": DB_MARKER}, ids=[1, 2, 3, 3, -1])
        self.assertEqual(code, 0)
        factory.assert_not_called()                         # Bot yaratilmaydi => Telegram'ga so'rov yo'q
        self.assertIn("DRY-RUN", out)
        self.assertIn("Jami foydalanuvchilar: 3", out)      # takror va manfiy ID olib tashlangan
        fetch.assert_called_once()

    def test_missing_token_in_real_mode_fails_before_touching_db(self):
        code, out, fetch, factory = self.run_main(env={"DATABASE_URL": DB_MARKER})
        self.assertEqual(code, 2)
        self.assertIn("BOT_TOKEN", out)
        fetch.assert_not_called()
        factory.assert_not_called()

    def test_database_error_message_is_not_printed(self):
        code, out, _, factory = self.run_main(fetch=RuntimeError(f"could not connect to {DB_MARKER}"))
        self.assertEqual(code, 1)
        self.assertIn("RuntimeError", out)                  # faqat xato turi
        self.assertNotIn("SECRET-DB-PASSWORD", out)
        self.assertNotIn(DB_MARKER, out)
        factory.assert_not_called()

    def test_secrets_never_appear_in_output(self):
        bot = self.real_bot({2: [RuntimeError(f"failed {TOKEN_MARKER} {DB_MARKER}")],
                             3: [TelegramBadRequest(METHOD, "Bad Request: chat not found")]})
        code, out, _, _ = self.run_main(ids=[1, 2, 3], bot=bot)
        self.assertEqual(code, 0)
        for secret in (TOKEN_MARKER, "SECRET-BOT-TOKEN", DB_MARKER, "SECRET-DB-PASSWORD"):
            self.assertNotIn(secret, out)

    def test_invalid_token_exit_code_1(self):
        bot = self.real_bot({1: [TelegramUnauthorizedError(METHOD, "Unauthorized")]})
        code, out, _, _ = self.run_main(ids=[1, 2, 3], bot=bot)
        self.assertEqual(code, 1)
        self.assertIn("BOT_TOKEN yaroqsiz", out)
        self.assertNotIn(TOKEN_MARKER, out)

    def test_clean_user_ids(self):
        self.assertEqual(rmb._clean_user_ids([3, "4", 3, -5, None, "x", 0, 12.0]), [3, 4, 12])
        self.assertEqual(rmb._clean_user_ids(None), [])


if __name__ == "__main__":
    unittest.main()
