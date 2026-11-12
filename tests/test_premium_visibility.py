"""
test_premium_visibility.py — Premium ko'rinib turishi (bot): yagona holat (admin_premium_view), qolgan kun,
reply menyu tugmasi (B5), /start salomi (B6), "Mening obunam" sahifasi (B7), tugashidan oldingi eslatma (B8),
shaxsiy menyu tugmasi (B9).

DB mantig'i HAQIQIY SQL bilan (tests/sqlite_db.py); Telegram va haqiqiy baza ishlatilmaydi.
Mini app (A0–A4) — tests/test_miniapp_api.py va tests/test_miniapp_premium_visibility_e2e.py.
"""
import asyncio
import datetime as dt
import os
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest import mock

from aiogram import types

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("BOT_TOKEN", "123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567890")
os.environ.setdefault("GEMINI_API_KEY", "test_gemini_key")

import bot as bot_mod  # noqa: E402
import database  # noqa: E402
from tests.sqlite_db import SqliteDB  # noqa: E402

UZ = dt.timezone(dt.timedelta(hours=5))
NOW = dt.datetime(2026, 11, 12, 12, 0, tzinfo=UZ)
UID = 900000801
APP_URL = "https://app.example/index.html"


def iso(**delta):
    return (NOW + dt.timedelta(**delta)).isoformat()


def view(tier=None, unlimited=False, **delta):
    """admin_premium_view natijasi, NOW ga nisbatan."""
    if tier is None:
        return database.admin_premium_view(0, None, None, NOW)
    return database.admin_premium_view(1, tier, None if unlimited else iso(**delta), NOW)


def labels(markup):
    return [b.text for row in markup.keyboard for b in row]


async def drain():
    tasks = list(bot_mod._menu_reset_tasks)
    if tasks:
        await asyncio.wait(tasks, timeout=2)


def reset_caches():
    bot_mod._menu_reset_done.clear()
    bot_mod._menu_premium_done.clear()
    bot_mod._premium_menu_cache.clear()
    bot_mod._pm_recent.clear()


# ───────────────────────────── yagona holat va qolgan kun ─────────────────────────────
class PremiumViewTest(unittest.TestCase):
    def test_states(self):
        free = view()
        self.assertEqual((free["active"], free["tier"], free["unlimited"], free["days_left"]), (False, "free", False, None))
        for tier in ("pro", "plus", "ultra"):
            v = view(tier, days=5)
            self.assertEqual((v["active"], v["tier"], v["unlimited"], v["days_left"]), (True, tier, False, 5), tier)
        unlimited = view("plus", unlimited=True)
        self.assertEqual((unlimited["active"], unlimited["tier"], unlimited["unlimited"], unlimited["expires"],
                          unlimited["days_left"], unlimited["ends_today"]), (True, "plus", True, None, None, False))

    def test_expired_flag_is_free(self):
        v = database.admin_premium_view(1, "ultra", iso(seconds=-1), NOW)
        self.assertEqual((v["active"], v["tier"], v["days_left"]), (False, "free", None))
        self.assertFalse(database.admin_premium_view(1, "pro", "buzuq-sana", NOW)["active"])

    def test_days_left_is_ceil_of_remaining_days(self):
        cases = [({"days": 5}, 5, False), ({"hours": 48}, 2, False), ({"hours": 25}, 2, False),
                 ({"hours": 24, "seconds": 1}, 2, False), ({"hours": 24}, 1, False),          # aniq 24 soat: hali "bugun" emas
                 ({"hours": 23, "minutes": 59, "seconds": 59}, 1, True), ({"hours": 3}, 1, True),
                 ({"minutes": 1}, 1, True), ({"days": 90}, 90, False)]
        for delta, left, today in cases:
            with self.subTest(delta=delta):
                v = view("ultra", **delta)
                self.assertEqual((v["days_left"], v["ends_today"]), (left, today))

    def test_premium_days_left_function(self):
        self.assertEqual(database.premium_days_left(NOW + dt.timedelta(days=5), NOW), 5)
        self.assertEqual(database.premium_days_left(NOW + dt.timedelta(hours=3), NOW), 1)
        self.assertEqual(database.premium_days_left(NOW - dt.timedelta(hours=3), NOW), 0)

    def test_unknown_tier_follows_quota_rule(self):
        self.assertEqual(database.admin_premium_view(1, "free", None, NOW)["tier"], "ultra")

    def test_tier_names_and_symbols_are_the_same_everywhere(self):
        titles = bot_mod.PREMIUM_TIER_TITLES
        # ICHKI kod pro = ko'rinadigan Plus, plus = Pro (database.TIER_DISPLAY / TIER_ICON)
        self.assertEqual(titles, {"pro": "⭐ Premium Plus", "plus": "💎 Premium Pro", "ultra": "👑 Premium Ultra"})
        self.assertEqual(set(titles), set(database._ADMIN_TIERS))
        self.assertEqual({entry[0] for entry in bot_mod.get_stars_tariffs().values()}, set(titles))
        for tier, label in bot_mod.PM_TIER_LABELS.items():                  # admin paneli: ⭐ Plus, 💎 Pro, 👑 Ultra
            self.assertEqual(titles[tier], label.replace(" ", " Premium ", 1))


class GetPremiumViewDbTest(unittest.TestCase):
    def setUp(self):
        self.db = SqliteDB()
        self.addCleanup(self.db.close)
        patcher = self.db.patched()
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_reads_real_state_without_side_effects(self):
        self.db.add_user(1, is_premium=1, premium_type="plus", premium_expires_at=(dt.datetime.now(UZ) + dt.timedelta(days=4)).isoformat())
        self.db.add_user(2, is_premium=1, premium_type="ultra", premium_expires_at=None)
        self.db.add_user(3, is_premium=1, premium_type="pro", premium_expires_at="2020-01-01T00:00:00+05:00")
        self.db.add_user(4)
        v1, v2, v3, v4 = (database.get_premium_view(i) for i in (1, 2, 3, 4))
        self.assertEqual((v1["active"], v1["tier"], v1["days_left"]), (True, "plus", 4))
        self.assertEqual((v2["active"], v2["tier"], v2["unlimited"]), (True, "ultra", True))
        self.assertEqual((v3["active"], v3["tier"]), (False, "free"))             # muddati o'tgan flag — oddiy
        self.assertFalse(v4["active"])
        self.assertEqual(self.db.row(3)["is_premium"], 1)                          # o'qish hech narsani o'zgartirmaydi
        self.assertFalse(database.get_premium_view(999)["active"])                 # bazada yo'q — oddiy, yozuv yaratilmaydi
        self.assertIsNone(self.db.row(999))


# ───────────────────────────── B5: reply menyu ─────────────────────────────
class KeyboardTest(unittest.TestCase):
    def setUp(self):
        reset_caches()
        self.addCleanup(reset_caches)

    def premium_label(self, markup):
        found = [t for t in labels(markup) if "Premium" in t]
        self.assertEqual(len(found), 1)
        return found[0]

    def test_label_follows_the_tier(self):
        self.assertEqual(self.premium_label(bot_mod.get_start_keyboard()), "💎 Premium")
        self.assertEqual(self.premium_label(bot_mod.get_start_keyboard(None)), "💎 Premium")
        self.assertEqual(self.premium_label(bot_mod.get_start_keyboard(view())), "💎 Premium")
        expected = {"pro": "⭐ Premium Plus", "plus": "💎 Premium Pro", "ultra": "👑 Premium Ultra"}
        for tier, text in expected.items():
            self.assertEqual(self.premium_label(bot_mod.get_start_keyboard(view(tier, days=5))), text)
        self.assertEqual(self.premium_label(bot_mod.get_start_keyboard(view("ultra", unlimited=True))), "👑 Premium Ultra")

    def test_day_count_is_never_written_into_the_keyboard(self):
        for v in (view("ultra", days=5), view("pro", hours=3), view("plus", unlimited=True)):
            text = self.premium_label(bot_mod.get_start_keyboard(v))
            self.assertFalse(any(ch.isdigit() for ch in text), text)
            self.assertNotIn("kun", text)
            self.assertNotIn("♾", text)

    def test_other_buttons_are_unchanged(self):
        base = [t for t in labels(bot_mod.get_start_keyboard()) if "Premium" not in t]
        for v in (None, view("pro", days=2), view("ultra", unlimited=True)):
            self.assertEqual([t for t in labels(bot_mod.get_start_keyboard(v)) if "Premium" not in t], base)
        self.assertEqual(len(base), 11)

    def test_texts_come_from_one_constant(self):
        seen = {self.premium_label(bot_mod.get_start_keyboard(v))
                for v in (None, view(), view("pro", days=1), view("plus", days=1), view("ultra", days=1))}
        self.assertEqual(seen, set(bot_mod.PREMIUM_BUTTON_TEXTS))
        self.assertEqual(len(bot_mod.PREMIUM_BUTTON_TEXTS), 4)

    def test_cache_gives_real_state_where_db_is_unavailable(self):
        with mock.patch.object(database, "get_connection", side_effect=AssertionError("DB'ga murojaat qilinmasligi kerak")):
            self.assertEqual(self.premium_label(bot_mod.get_start_keyboard_for(UID)), "💎 Premium")        # noma'lum
            bot_mod.remember_premium_state(UID, view("ultra", days=5))
            self.assertEqual(self.premium_label(bot_mod.get_start_keyboard_for(UID)), "👑 Premium Ultra")
            bot_mod.remember_premium_state(UID, view("plus", days=5))
            self.assertEqual(self.premium_label(bot_mod.get_start_keyboard_for(UID)), "💎 Premium Pro")
            bot_mod.remember_premium_state(UID, view())                                                     # Premium tugadi
            self.assertEqual(self.premium_label(bot_mod.get_start_keyboard_for(UID)), "💎 Premium")
            bot_mod.remember_premium_state(UID, view("ultra", days=5))
            bot_mod.remember_premium_state(UID, None)                                                       # holat noma'lum — o'zgarmaydi
            self.assertEqual(self.premium_label(bot_mod.get_start_keyboard_for(UID)), "👑 Premium Ultra")

    def test_cache_entries_expire(self):
        bot_mod.remember_premium_state(UID, view("ultra", days=5))
        with mock.patch.object(bot_mod.time, "monotonic", return_value=bot_mod.time.monotonic() + bot_mod.PREMIUM_MENU_CACHE_TTL + 1):
            self.assertIsNone(bot_mod.cached_premium_view(UID))
            self.assertEqual(self.premium_label(bot_mod.get_start_keyboard_for(UID)), "💎 Premium")

    def test_payment_flow_only_gains_menu_refresh(self):
        """To'lov mantig'i o'zgarmagan (validate_payment, process_paid_premium, takroriy to'lov himoyasi, reconcile);
        faqat javob xabariga yangi holatdagi klaviatura qo'shilgan va menyu keshi/shaxsiy tugma yangilanadi."""
        import inspect
        src = inspect.getsource(bot_mod.process_successful_payment)
        for kept in ("validate_payment(payload, payment.currency, payment.total_amount)",
                     "database.process_paid_premium", "payload == DISCOUNT_PAYLOAD", "record_failed_payment",
                     "Bu to'lov allaqachon qayta ishlangan"):
            self.assertIn(kept, src)
        self.assertIn("refresh_premium_menu", src)
        self.assertIn("reply_markup=get_start_keyboard(new_view)", src)


class MenuTextRoutingTest(unittest.IsolatedAsyncioTestCase):
    def premium_handler_filter(self):
        handler = next(h for h in bot_mod.dp.message.handlers if h.callback is bot_mod.reply_premium_info)
        self.assertEqual(len(handler.filters), 1)
        return handler.filters[0].callback

    async def test_every_premium_button_text_goes_to_the_premium_handler(self):
        matches = self.premium_handler_filter()
        for text in bot_mod.PREMIUM_BUTTON_TEXTS:
            with self.subTest(text=text):
                self.assertTrue(matches(SimpleNamespace(text=text)))
        for text in ("💎 Premium Max", "Premium", "👑 Ilova", "Salom", "⭐ Premium Pro 5 kun"):
            self.assertFalse(matches(SimpleNamespace(text=text)), text)

    async def test_premium_texts_are_never_treated_as_ai_questions(self):
        for text in bot_mod.PREMIUM_BUTTON_TEXTS:
            with self.subTest(text=text):
                message = mock.MagicMock()
                message.text = text
                message.from_user = SimpleNamespace(id=UID)
                message.answer = mock.AsyncMock()
                message.reply = mock.AsyncMock()
                with mock.patch.object(bot_mod.medicine_db, "find_medicine") as find, \
                        mock.patch.object(bot_mod, "get_gemini_response", mock.AsyncMock()) as ai:
                    await bot_mod.handle_ai_chat(message, mock.MagicMock())
                find.assert_not_called()
                ai.assert_not_awaited()
                message.answer.assert_not_awaited()

    async def test_premium_texts_leave_fsm_states(self):
        middleware = bot_mod.FsmResetMiddleware()
        for text in bot_mod.PREMIUM_BUTTON_TEXTS:
            with self.subTest(text=text):
                event = mock.MagicMock(spec=types.Message)
                event.text = text
                state = mock.MagicMock()
                state.clear = mock.AsyncMock()
                handler = mock.AsyncMock(return_value="ok")
                self.assertEqual(await middleware(handler, event, {"state": state}), "ok")
                state.clear.assert_awaited_once()
        event = mock.MagicMock(spec=types.Message)
        event.text = "oddiy savol"
        state = mock.MagicMock()
        state.clear = mock.AsyncMock()
        await middleware(mock.AsyncMock(), event, {"state": state})
        state.clear.assert_not_awaited()

    async def test_other_replies_use_cached_tier_without_db(self):
        reset_caches()
        self.addCleanup(reset_caches)
        bot_mod.remember_premium_state(UID, view("plus", days=9))
        message = mock.MagicMock()
        message.from_user = SimpleNamespace(id=UID)
        message.answer = mock.AsyncMock()
        state = mock.MagicMock()
        state.clear = mock.AsyncMock()
        with mock.patch.object(database, "get_connection", side_effect=AssertionError("DB yo'q")):
            await bot_mod.cmd_menu(message, state)
        self.assertIn("💎 Premium Pro", labels(message.answer.await_args.kwargs["reply_markup"]))
        callback = mock.MagicMock()
        callback.from_user = SimpleNamespace(id=UID)
        callback.message.answer = mock.AsyncMock()
        callback.message.edit_text = mock.AsyncMock()
        callback.answer = mock.AsyncMock()
        state2 = mock.MagicMock()
        state2.clear = mock.AsyncMock()
        await bot_mod.back_to_main(callback, state2)                                 # callback: foydalanuvchi callback.from_user dan
        self.assertIn("💎 Premium Pro", labels(callback.message.answer.await_args.kwargs["reply_markup"]))


# ───────────────────────────── B6 + B9: /start ─────────────────────────────
class StartTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        reset_caches()
        self.addCleanup(reset_caches)
        self.menu_call = mock.AsyncMock(return_value=True)
        self.fake_bot = SimpleNamespace(set_chat_menu_button=self.menu_call)
        patcher = mock.patch.dict(os.environ, {"MINI_APP_URL": APP_URL})
        patcher.start()
        self.addCleanup(patcher.stop)

    async def start(self, premium_view, text="/start"):
        message = mock.MagicMock()
        message.text = text
        message.from_user = SimpleNamespace(id=UID, first_name="Ali", last_name=None, username="ali")
        message.answer = mock.AsyncMock()
        message.bot = self.fake_bot
        state = mock.MagicMock()
        state.clear = mock.AsyncMock()
        with mock.patch.object(database, "register_user"), \
                mock.patch.object(database, "get_premium_view", return_value=premium_view):
            await bot_mod.cmd_start(message, state)
        await drain()
        return message

    def greeting(self, message):
        return message.answer.await_args_list[-1].args[0]

    # ---- B6: salom ----
    async def test_premium_user_gets_one_extra_line(self):
        free_text = self.greeting(await self.start(view()))
        for tier, title in (("pro", "⭐ Premium Plus"), ("plus", "💎 Premium Pro"), ("ultra", "👑 Premium Ultra")):
            with self.subTest(tier=tier):
                reset_caches()
                text = self.greeting(await self.start(view(tier, days=33)))
                line = f"{title} faol — 15.12.2026 gacha"
                self.assertIn(line, text)
                self.assertEqual(text.replace(line + "\n\n", ""), free_text)         # faqat BITTA qator qo'shildi

    async def test_unlimited_premium_line(self):
        text = self.greeting(await self.start(view("ultra", unlimited=True)))
        self.assertIn("👑 Premium Ultra faol — muddatsiz", text)
        self.assertNotIn("gacha", text)

    async def test_free_user_greeting_is_unchanged(self):
        text = self.greeting(await self.start(view()))
        self.assertNotIn("faol —", text)
        self.assertNotIn("Premium Pro", text)
        self.assertNotIn("Premium Plus", text)
        expired = self.greeting(await self.start(database.admin_premium_view(1, "ultra", iso(days=-1), NOW)))
        self.assertEqual(expired, text)

    async def test_start_keyboard_label_follows_tier(self):
        message = await self.start(view("ultra", days=5))
        self.assertIn("👑 Premium Ultra", labels(message.answer.await_args_list[-1].kwargs["reply_markup"]))
        free = await self.start(view())
        self.assertIn("💎 Premium", labels(free.answer.await_args_list[-1].kwargs["reply_markup"]))

    async def test_deep_link_paths_use_the_same_keyboard(self):
        with mock.patch.object(database, "check_and_grant_daily_bonus", return_value=(False, 0, 0)):
            message = await self.start(view("plus", days=5), text="/start claim_daily")
        self.assertIn("💎 Premium Pro", labels(message.answer.await_args.kwargs["reply_markup"]))

    async def test_db_failure_does_not_break_start(self):
        message = mock.MagicMock()
        message.text = "/start"
        message.from_user = SimpleNamespace(id=UID, first_name="Ali", last_name=None, username="ali")
        message.answer = mock.AsyncMock()
        message.bot = self.fake_bot
        state = mock.MagicMock()
        state.clear = mock.AsyncMock()
        with mock.patch.object(database, "register_user"), \
                mock.patch.object(database, "get_premium_view", side_effect=RuntimeError("SECRET-DB")), \
                self.assertLogs(level="WARNING") as logs:
            await bot_mod.cmd_start(message, state)
        await drain()
        self.assertIn("💎 Premium", labels(message.answer.await_args.kwargs["reply_markup"]))   # eski ko'rinish
        self.assertNotIn("SECRET-DB", "\n".join(logs.output))
        self.assertIsInstance(self.menu_call.await_args.kwargs["menu_button"], types.MenuButtonDefault)

    # ---- B9: shaxsiy menyu tugmasi ----
    async def test_premium_gets_personal_app_button(self):
        await self.start(view("ultra", days=5))
        self.menu_call.assert_awaited_once()
        kwargs = self.menu_call.await_args.kwargs
        self.assertEqual(kwargs["chat_id"], UID)
        button = kwargs["menu_button"]
        self.assertIsInstance(button, types.MenuButtonWebApp)
        self.assertEqual(button.text, "👑 Ilova")
        self.assertEqual(button.web_app.url, APP_URL)
        self.assertNotIn("?", button.web_app.url)                                  # query parametr yo'q: faqat MINI_APP_URL

    async def test_free_gets_default_as_before(self):
        await self.start(view())
        self.assertIsInstance(self.menu_call.await_args.kwargs["menu_button"], types.MenuButtonDefault)

    async def test_not_repeated_for_same_premium_user(self):
        await self.start(view("pro", days=3))
        await self.start(view("pro", days=3))
        self.assertEqual(self.menu_call.await_count, 1)

    async def test_premium_that_ended_goes_back_to_default_on_next_start(self):
        await self.start(view("ultra", days=1))
        self.assertIsInstance(self.menu_call.await_args.kwargs["menu_button"], types.MenuButtonWebApp)
        await self.start(view())                                                   # Premium tugadi (yoki olib tashlandi)
        self.assertEqual(self.menu_call.await_count, 2)
        self.assertIsInstance(self.menu_call.await_args.kwargs["menu_button"], types.MenuButtonDefault)
        await self.start(view())
        self.assertEqual(self.menu_call.await_count, 2)                            # Default takror yuborilmaydi

    async def test_free_user_who_got_premium_gets_button_even_after_default_was_sent(self):
        await self.start(view())
        await self.start(view("plus", days=5))
        self.assertEqual(self.menu_call.await_count, 2)
        self.assertIsInstance(self.menu_call.await_args.kwargs["menu_button"], types.MenuButtonWebApp)

    async def test_slow_telegram_does_not_delay_start_for_premium(self):
        gate = asyncio.Event()

        async def blocked(**kwargs):
            await gate.wait()

        self.menu_call.side_effect = blocked
        message = mock.MagicMock()
        message.text = "/start"
        message.from_user = SimpleNamespace(id=UID, first_name="Ali", last_name=None, username="ali")
        message.answer = mock.AsyncMock()
        message.bot = self.fake_bot
        state = mock.MagicMock()
        state.clear = mock.AsyncMock()
        with mock.patch.object(bot_mod, "MENU_RESET_TIMEOUT", 30.0), mock.patch.object(database, "register_user"), \
                mock.patch.object(database, "get_premium_view", return_value=view("ultra", days=5)):
            await bot_mod.cmd_start(message, state)
            pending = list(bot_mod._menu_reset_tasks)
            message.answer.assert_awaited()                                        # /start javob berdi
            self.assertEqual(len(pending), 1)
            self.assertFalse(pending[0].done())                                    # fon vazifasi hali tugamagan
            gate.set()
            await drain()


class PersonalMenuButtonTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        reset_caches()
        self.addCleanup(reset_caches)
        self.call = mock.AsyncMock(return_value=True)
        self.fake = SimpleNamespace(set_chat_menu_button=self.call)
        patcher = mock.patch.dict(os.environ, {"MINI_APP_URL": APP_URL})
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_premium_then_default_then_default_again(self):
        await bot_mod.apply_personal_menu_button(self.fake, UID, True)
        self.assertIsInstance(self.call.await_args.kwargs["menu_button"], types.MenuButtonWebApp)
        await bot_mod.apply_personal_menu_button(self.fake, UID, False)
        self.assertIsInstance(self.call.await_args.kwargs["menu_button"], types.MenuButtonDefault)
        self.assertEqual(self.call.await_count, 2)
        await bot_mod.apply_personal_menu_button(self.fake, UID, False)             # takroriy tozalash yuborilmaydi
        self.assertEqual(self.call.await_count, 2)

    async def test_forced_default_ignores_the_already_reset_mark(self):
        bot_mod._menu_reset_done.add(UID)
        await bot_mod.apply_personal_menu_button(self.fake, UID, False)
        self.call.assert_not_awaited()
        await bot_mod.apply_personal_menu_button(self.fake, UID, False, force=True)
        self.assertIsInstance(self.call.await_args.kwargs["menu_button"], types.MenuButtonDefault)

    async def test_without_mini_app_url_falls_back_to_default(self):
        with mock.patch.dict(os.environ, {"MINI_APP_URL": ""}), mock.patch.object(bot_mod, "MINI_APP_URL", ""):
            await bot_mod.apply_personal_menu_button(self.fake, UID, True)
        self.assertIsInstance(self.call.await_args.kwargs["menu_button"], types.MenuButtonDefault)

    async def test_telegram_errors_are_only_logged(self):
        self.call.side_effect = RuntimeError("boom SECRET-MARKER")
        with self.assertLogs(level="WARNING") as logs:
            await bot_mod.apply_personal_menu_button(self.fake, UID, True)
        joined = "\n".join(logs.output)
        self.assertIn("Premium menyu tugmasini qo'yib bo'lmadi", joined)
        self.assertIn("RuntimeError", joined)
        self.assertNotIn("SECRET-MARKER", joined)                                   # xato matni emas, turi
        self.assertNotIn(UID, bot_mod._menu_premium_done)                           # muvaffaqiyatsiz: belgilanmaydi (qayta uriniladi)

    async def test_timeout_is_applied(self):
        gate = asyncio.Event()

        async def blocked(**kwargs):
            await gate.wait()

        self.call.side_effect = blocked
        with mock.patch.object(bot_mod, "MENU_RESET_TIMEOUT", 0.05), self.assertLogs(level="WARNING") as logs:
            await bot_mod.apply_personal_menu_button(self.fake, UID, True)
        self.assertIn("TimeoutError", " | ".join(logs.output))

    async def test_schedule_runs_in_background(self):
        bot_mod.schedule_personal_menu_sync(self.fake, UID, True)
        self.assertEqual(len(bot_mod._menu_reset_tasks), 1)
        await drain()
        self.call.assert_awaited_once()
        self.assertEqual(len(bot_mod._menu_reset_tasks), 0)


# ───────────────────────────── B7: "Mening obunam" ─────────────────────────────
class MyPremiumPageTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        reset_caches()
        self.addCleanup(reset_caches)
        patcher = mock.patch.dict(os.environ, {"MINI_APP_URL": APP_URL, "PRO_MONTHLY_STARS": "150"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def message(self):
        m = mock.MagicMock()
        m.from_user = SimpleNamespace(id=UID)
        m.answer = mock.AsyncMock()
        return m

    def callback(self):
        cb = mock.MagicMock(spec=types.CallbackQuery)
        cb.from_user = SimpleNamespace(id=UID)
        cb.message = mock.MagicMock()
        cb.message.edit_text = mock.AsyncMock()
        cb.message.answer = mock.AsyncMock()
        cb.answer = mock.AsyncMock()
        return cb

    async def page(self, v, quota=(14, 30, 2), discount=False, target=None):
        target = target or self.message()
        with mock.patch.object(database, "get_premium_view", return_value=v), \
                mock.patch.object(database, "get_ai_quota_detail", return_value=quota), \
                mock.patch.object(database, "has_discount", return_value=discount), \
                mock.patch.object(database, "get_score", return_value=7), \
                mock.patch.object(bot_mod, "get_web_app_url", mock.AsyncMock(return_value="https://x/app")):
            await bot_mod._show_premium_page(target)
        return target

    def sent(self, target):
        if isinstance(target, types.CallbackQuery):
            args, kwargs = target.message.edit_text.await_args
        else:
            args, kwargs = target.answer.await_args
        return args[0], kwargs["reply_markup"]

    def buttons(self, markup):
        return [(b.text, b.callback_data, getattr(b.web_app, "url", None)) for row in markup.inline_keyboard for b in row]

    async def test_premium_user_sees_subscription_not_sales(self):
        text, markup = self.sent(await self.page(view("ultra", days=5)))
        for part in ("Mening obunam", "👑 Premium Ultra", "17.11.2026", "5 kun qoldi", "<b>12/30</b> (+ 2 bonus)"):
            self.assertIn(part, text)
        self.assertNotIn("TARIFLARI", text)
        self.assertEqual(self.buttons(markup),
                         [("🔄 Uzaytirish", "premium_extend", None), ("🚑 Mini ilovada ochish", None, APP_URL)])

    async def test_ai_limit_without_bonus_has_no_bonus_part(self):
        text, _ = self.sent(await self.page(view("pro", days=3), quota=(12, 15, 0)))
        self.assertIn("<b>12/15</b>", text)
        self.assertNotIn("bonus", text)

    async def test_unlimited_premium_no_longer_falls_into_sales_page(self):
        # Xato: muddatsiz Premium (muddat bo'sh) ilgari sotuv sahifasiga tushib qolardi
        for tier in ("pro", "plus", "ultra"):
            with self.subTest(tier=tier):
                text, markup = self.sent(await self.page(view(tier, unlimited=True)))
                self.assertIn("Mening obunam", text)
                self.assertIn("Muddatsiz", text)
                self.assertNotIn("TARIFLARI", text)
                self.assertNotIn("gacha", text)
                # muddatsiz Premiumga muddat qo'shib bo'lmaydi: "Uzaytirish" tugmasi yo'q
                self.assertNotIn("premium_extend", [b[1] for b in self.buttons(markup)])

    async def test_last_day_says_ends_today(self):
        text, _ = self.sent(await self.page(view("plus", hours=3)))
        self.assertIn("bugun tugaydi", text)
        self.assertNotIn("kun qoldi", text)

    async def test_expired_flag_and_free_users_get_the_sales_page(self):
        for v in (view(), database.admin_premium_view(1, "ultra", iso(days=-1), NOW)):
            with self.subTest(view=v["active"]):
                text, markup = self.sent(await self.page(v))
                self.assertIn("PREMIUM OBS TARIFLARI", text)
                self.assertNotIn("Mening obunam", text)
                callbacks = [b[1] for b in self.buttons(markup)]
                for needed in ("buy_pro_7", "buy_plus_30", "buy_ultra_30"):
                    self.assertIn(needed, callbacks)

    async def test_super_prize_discount_logic_is_kept(self):
        _, markup = self.sent(await self.page(view("pro", days=5), discount=True))
        self.assertEqual(self.buttons(markup)[0][1], "buy_plus_30_discount")        # chegirma tugmasi birinchi
        text, _ = self.sent(await self.page(view("pro", days=5), discount=True))
        self.assertIn("SUPER PRIZ chegirmasi bor", text)
        # Faol ichki plus (ko'rinadigan Pro): chegirma UZAYTIRISH sifatida ishlaydi; ultra (pastroq tarif) — yo'q
        text, markup = self.sent(await self.page(view("plus", days=5), discount=True))
        self.assertEqual(self.buttons(markup)[0][:2], ("🎁 Premium Pro — yana 30 kun (75 ⭐, -50%)", "buy_plus_30_discount"))
        _, markup = self.sent(await self.page(view("ultra", days=5), discount=True))
        self.assertNotIn("buy_plus_30_discount", [b[1] for b in self.buttons(markup)])
        _, markup = self.sent(await self.page(view("pro", days=5), discount=False))
        self.assertNotIn("buy_plus_30_discount", [b[1] for b in self.buttons(markup)])

    async def test_open_app_button_hidden_without_url(self):
        with mock.patch.dict(os.environ, {"MINI_APP_URL": ""}), mock.patch.object(bot_mod, "MINI_APP_URL", ""):
            _, markup = self.sent(await self.page(view("ultra", days=5)))
        self.assertEqual([b[0] for b in self.buttons(markup)], ["🔄 Uzaytirish"])

    async def test_page_updates_menu_keyboard_cache(self):
        await self.page(view("ultra", days=5))
        self.assertEqual(bot_mod.cached_premium_view(UID), {"active": True, "tier": "ultra"})
        await self.page(view())
        self.assertEqual(bot_mod.cached_premium_view(UID), {"active": False, "tier": "free"})

    async def test_callback_flow_edits_the_message(self):
        cb = await self.page(view("plus", days=4), target=self.callback())
        text, _ = self.sent(cb)
        self.assertIn("Mening obunam", text)
        cb.answer.assert_awaited()

    async def test_extend_button_opens_tariff_list(self):
        cb = self.callback()
        with mock.patch.object(database, "has_discount", return_value=False), \
                mock.patch.object(database, "get_score", return_value=7), \
                mock.patch.object(bot_mod, "get_web_app_url", mock.AsyncMock(return_value="https://x/app")):
            await bot_mod.process_premium_extend(cb)
        text, markup = self.sent(cb)
        self.assertIn("PREMIUM OBS TARIFLARI", text)
        self.assertEqual([b[1] for b in self.buttons(markup) if b[1] and b[1].startswith("buy_")],
                         ["buy_pro_7", "buy_plus_30", "buy_ultra_30"])              # mavjud xarid tugmalari


# ───────────────────────────── B8: tugashidan oldingi eslatma ─────────────────────────────
class ExpiryReminderTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        reset_caches()
        self.addCleanup(reset_caches)
        self.db = SqliteDB()
        self.addCleanup(self.db.close)
        self.fake_bot = mock.MagicMock()
        self.fake_bot.send_message = mock.AsyncMock()
        self.fake_bot.set_chat_menu_button = mock.AsyncMock()
        self.banned = set()
        patches = [
            self.db.patched(),
            mock.patch.object(bot_mod, "bot", self.fake_bot),
            mock.patch.object(bot_mod, "PREMIUM_EXPIRY_SEND_PAUSE", 0),
            mock.patch.object(database, "is_user_banned", side_effect=lambda uid: (uid in self.banned, "")),
            mock.patch.dict(os.environ, {"MINI_APP_URL": APP_URL}),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def add(self, uid, hours=None, tier="ultra", **cols):
        expires = iso(hours=hours) if hours is not None else None
        self.db.add_user(uid, is_premium=1, premium_type=tier, premium_expires_at=expires, full_name=f"U{uid}", **cols)

    async def check(self, now=NOW):
        stats = await bot_mod.run_premium_expiry_check(now)
        await drain()
        return stats

    def sent_to(self):
        return [c.args[0] for c in self.fake_bot.send_message.await_args_list]

    async def test_within_24h_one_message_then_none(self):
        self.add(1, hours=10)
        self.assertEqual(await self.check(), {"notified": 1, "failed": 0, "closed": 0})
        self.fake_bot.send_message.assert_awaited_once()
        args, kwargs = self.fake_bot.send_message.await_args
        self.assertEqual(args[0], 1)
        self.assertEqual(kwargs["parse_mode"], "HTML")
        button = kwargs["reply_markup"].inline_keyboard[0][0]
        self.assertEqual((button.text, button.callback_data), ("🔄 Uzaytirish", "premium_extend"))
        self.assertEqual(self.db.row(1)["premium_expiry_notified_for"], iso(hours=10))        # xabar yuborilgan muddat
        self.assertEqual(await self.check(), {"notified": 0, "failed": 0, "closed": 0})          # ikkinchi tekshiruv — xabar yo'q
        self.assertEqual(await self.check(NOW + dt.timedelta(hours=3)), {"notified": 0, "failed": 0, "closed": 0})
        self.assertEqual(self.fake_bot.send_message.await_count, 1)

    async def test_extension_makes_the_reminder_work_again(self):
        self.add(1, hours=10)
        await self.check()
        self.assertEqual(self.fake_bot.send_message.await_count, 1)
        # Admin / xarid orqali muddat uzaytirildi, keyin yana 24 soatdan kam qoldi
        self.db_extend(1, iso(hours=20))
        stats = await self.check()
        self.assertEqual(stats["notified"], 1)
        self.assertEqual(self.fake_bot.send_message.await_count, 2)
        self.assertEqual(self.db.row(1)["premium_expiry_notified_for"], iso(hours=20))
        await self.check()
        self.assertEqual(self.fake_bot.send_message.await_count, 2)

    def db_extend(self, uid, new_iso):
        import sqlite3
        con = sqlite3.connect(self.db.path)
        con.execute("UPDATE users SET premium_expires_at = ? WHERE user_id = ?", (new_iso, uid))
        con.commit()
        con.close()

    async def test_no_message_to_unlimited_free_banned_or_far_expiry(self):
        self.add(1, hours=None)                                                       # muddatsiz
        self.db.add_user(2, is_premium=0, premium_type="free", premium_expires_at=iso(hours=5))    # bepul
        self.add(3, hours=5)
        self.banned.add(3)                                                            # ban qilingan
        self.add(4, hours=30)                                                         # hali erta
        self.add(5, hours=24 * 20)
        stats = await self.check()
        self.assertEqual(stats, {"notified": 0, "failed": 0, "closed": 0})
        self.fake_bot.send_message.assert_not_awaited()
        self.assertIsNone(self.db.row(3)["premium_expiry_notified_for"])              # ban qilingan belgilanmadi: ban tugasa eslatma ketadi

    async def test_window_boundary(self):
        self.add(1, hours=24)
        self.add(2, hours=24)
        self.db_extend(2, (NOW + dt.timedelta(hours=24, seconds=1)).isoformat())
        await self.check()
        self.assertEqual(self.sent_to(), [1])                                         # aniq 24 soat kiradi, 24 soat + 1 s kirmaydi

    async def test_blocked_user_does_not_stop_the_task(self):
        for uid in (1, 2, 3):
            self.add(uid, hours=5)
        outcomes = {1: Exception("Forbidden: bot was blocked by the user"), 2: None, 3: None}

        async def send(uid, *args, **kwargs):
            if outcomes[uid]:
                raise outcomes[uid]

        self.fake_bot.send_message.side_effect = send
        with self.assertLogs(level="WARNING") as logs:
            stats = await self.check()
        self.assertEqual(stats, {"notified": 2, "failed": 1, "closed": 0})
        self.assertEqual(sorted(self.sent_to()), [1, 2, 3])                           # hammasiga urinildi
        self.assertIn("eslatma yetmadi (user=1)", "\n".join(logs.output))
        self.assertNotIn("blocked by the user", "\n".join(logs.output))               # xato matni emas, turi
        self.assertEqual(await self.check(), {"notified": 0, "failed": 0, "closed": 0})      # qayta-qayta urinilmaydi

    async def test_at_most_200_per_check_rest_next_time(self):
        for uid in range(1, 251):
            self.add(uid, hours=5)
        self.assertEqual((await self.check())["notified"], 200)
        self.assertEqual((await self.check())["notified"], 50)
        self.assertEqual((await self.check())["notified"], 0)
        self.assertEqual(len(set(self.sent_to())), 250)                               # har kim bir martadan

    async def test_text_says_today_or_tomorrow_with_tier_and_time(self):
        self.add(1, hours=6, tier="plus")                                             # 12.11 18:00 — bugun
        self.add(2, hours=21, tier="pro")                                             # 13.11 09:00 — ertaga
        self.add(3, hours=10, tier="ultra")                                           # 12.11 22:00 — bugun
        await self.check()
        texts = {c.args[0]: c.args[1] for c in self.fake_bot.send_message.await_args_list}
        self.assertEqual(texts[1], "⏳ Premium Pro obunangiz bugun (12.11.2026, 18:00) tugaydi. Uzaytirish uchun 👇")
        self.assertEqual(texts[2], "⏳ Premium Plus obunangiz ertaga (13.11.2026, 09:00) tugaydi. Uzaytirish uchun 👇")
        self.assertIn("Premium Ultra obunangiz bugun (12.11.2026, 22:00)", texts[3])

    async def test_atomic_mark_only_one_of_many_parallel_claims_wins(self):
        self.add(1, hours=5)
        barrier = threading.Barrier(20, timeout=10)

        def worker(_):
            barrier.wait()
            return database.claim_premium_expiry_notice(1, iso(hours=5))

        with ThreadPoolExecutor(max_workers=20) as pool:
            results = list(pool.map(worker, range(20)))
        self.assertEqual(sum(results), 1)
        self.assertFalse(database.claim_premium_expiry_notice(1, iso(hours=5)))       # shu muddat uchun qayta — yo'q
        self.assertTrue(database.claim_premium_expiry_notice(1, iso(hours=7)))        # boshqa muddat — yana mumkin

    async def test_two_parallel_checks_send_one_message(self):
        self.add(1, hours=5)
        stats = await asyncio.gather(bot_mod.run_premium_expiry_check(NOW), bot_mod.run_premium_expiry_check(NOW))
        self.assertEqual(sum(s["notified"] for s in stats), 1)
        self.assertEqual(self.fake_bot.send_message.await_count, 1)

    async def test_expired_premium_is_closed_menu_button_back_no_message(self):
        self.add(1, hours=-2)
        bot_mod._menu_premium_done.add(1)                                             # unda "👑 Ilova" tugmasi bor edi
        stats = await self.check()
        self.assertEqual(stats, {"notified": 0, "failed": 0, "closed": 1})
        self.fake_bot.send_message.assert_not_awaited()                               # xabar bormaydi
        row = self.db.row(1)
        self.assertEqual((row["is_premium"], row["premium_type"]), (0, "free"))
        self.fake_bot.set_chat_menu_button.assert_awaited_once()
        kwargs = self.fake_bot.set_chat_menu_button.await_args.kwargs
        self.assertEqual(kwargs["chat_id"], 1)
        self.assertIsInstance(kwargs["menu_button"], types.MenuButtonDefault)
        self.assertEqual(bot_mod.cached_premium_view(1), {"active": False, "tier": "free"})   # reply menyu ham eski ko'rinishga
        self.assertEqual(await self.check(), {"notified": 0, "failed": 0, "closed": 0})        # takroran emas
        self.assertEqual(self.fake_bot.set_chat_menu_button.await_count, 1)

    async def test_default_is_forced_even_if_marked_as_already_reset(self):
        self.add(1, hours=-2)
        bot_mod._menu_reset_done.add(1)
        await self.check()
        self.fake_bot.set_chat_menu_button.assert_awaited_once()

    async def test_extended_in_the_meantime_is_not_closed(self):
        self.add(1, hours=-2)
        stale = (await asyncio.to_thread(database.premium_expiry_candidates, NOW))["expired"]
        self.assertEqual(len(stale), 1)
        self.db_extend(1, iso(days=30))                                               # tekshiruv va yopish orasida uzaytirildi
        self.assertFalse(database.close_expired_premium(1, stale[0]["expires_raw"]))
        self.assertEqual(self.db.row(1)["is_premium"], 1)

    async def test_candidates_function_lists_exactly_the_right_users(self):
        self.add(1, hours=5)
        self.add(2, hours=-1)
        self.add(3, hours=None)
        self.add(4, hours=48)
        self.db.add_user(5, is_premium=0, premium_type="free", premium_expires_at=iso(hours=5))
        found = database.premium_expiry_candidates(NOW)
        self.assertEqual([u["user_id"] for u in found["notify"]], [1])
        self.assertEqual([u["user_id"] for u in found["expired"]], [2])
        self.assertEqual(found["notify"][0]["tier"], "ultra")

    async def test_loop_survives_errors_and_checks_hourly(self):
        runs = []

        async def fake_check():
            runs.append(1)
            if len(runs) == 1:
                raise RuntimeError("DB xatosi")
            return {}

        sleeps = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps) == 2:
                raise asyncio.CancelledError()

        with mock.patch.object(bot_mod, "run_premium_expiry_check", fake_check), \
                mock.patch.object(bot_mod.asyncio, "sleep", fake_sleep), self.assertLogs(level="ERROR"):
            with self.assertRaises(asyncio.CancelledError):
                await bot_mod.premium_expiry_loop()
        self.assertEqual(len(runs), 2)                                                # birinchi xatodan keyin davom etdi
        self.assertEqual(sleeps, [3600.0, 3600.0])                                    # soatiga bir marta

    async def test_loop_is_registered_in_main_for_both_modes(self):
        import inspect
        src = inspect.getsource(bot_mod.main)
        self.assertIn("premium_expiry_loop()", src)
        self.assertLess(src.index("premium_expiry_loop()"), src.index("run_webhook"))   # webhook/polling tarmog'idan oldin


class ExpiryMigrationTest(unittest.TestCase):
    def test_init_db_adds_the_notified_column(self):
        cursor = mock.MagicMock()
        executed = []
        cursor.execute.side_effect = lambda sql, params=(): executed.append(" ".join(sql.split()))
        cm = mock.MagicMock()
        cm.__enter__.return_value = (mock.MagicMock(), cursor)
        with mock.patch.object(database, "_managed_cursor", return_value=cm):
            database.init_db()
        self.assertIn("ALTER TABLE users ADD COLUMN IF NOT EXISTS premium_expiry_notified_for TEXT", executed)
        create_users = next(q for q in executed if q.startswith("CREATE TABLE IF NOT EXISTS users"))
        self.assertIn("premium_expiry_notified_for TEXT", create_users)

    def test_marking_uses_a_parametrized_conditional_update(self):
        import inspect
        src = inspect.getsource(database.claim_premium_expiry_notice)
        self.assertIn("IS DISTINCT FROM", src)
        self.assertIn("rowcount", src)
        self.assertNotIn('f"UPDATE', src)


if __name__ == "__main__":
    unittest.main()
