"""
test_ban_system.py — ban tizimi: 📣 ochiq va 🤫 sirli ban.

  * DB (HAQIQIY SQL, tests/sqlite_db.py): ban/unban ikkala rejimda, eski ban (ban_mode NULL) = ochiq, muddati o'tgan ban
    o'qishda "yo'q" lekin bazadan tozalanmaydi, kesh invalidatsiyasi, fon tozalash (atomar), ommaviy tanlov shartlari;
  * BanMiddleware: ochiq — xabar va alert; sirli — HECH NARSA (message / callback / throttling / AnswerCallback);
    pre_checkout; middleware tartibi (Ban -> Throttling);
  * API: ochiq 403 `banned` (+ muddat / sabab / murojaat), sirli — oddiy server xatosidan farq qilmaydi;
  * fon vazifasi: ochiq — bitta xabar, sirli — xabarsiz, parallel chaqiruvda bir marta.
Admin paneli — tests/test_ban_panel.py, ommaviy yuborishlar — tests/test_ban_broadcasts.py. Telegram soxta.
"""
import asyncio
import datetime as dt
import os
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest import mock

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("BOT_TOKEN", "123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567890")
os.environ.setdefault("GEMINI_API_KEY", "test_gemini_key")

from aiogram import Dispatcher, types  # noqa: E402

import bot as bot_mod  # noqa: E402
import database  # noqa: E402
from tests.sqlite_db import SqliteDB  # noqa: E402
from tests.test_miniapp_api import ApiTestBase, USER_ID as API_USER  # noqa: E402

UZ = dt.timezone(dt.timedelta(hours=5))
UID = 700001
OPEN_INFO = {"banned": True, "mode": "open", "until": None, "reason": None}
SILENT_INFO = {"banned": True, "mode": "silent", "until": None, "reason": None}
FREE_INFO = {"banned": False, "mode": None, "until": None, "reason": None}


def naive_wall(**delta):
    """Toshkent devor soati (zonasiz) ISO — TIMESTAMP ustuni qiymati."""
    return (database.get_uz_now() + dt.timedelta(**delta)).replace(tzinfo=None).isoformat()


class BanDbCase(unittest.TestCase):
    def setUp(self):
        self.db = SqliteDB()
        self.addCleanup(self.db.close)
        for patcher in (self.db.patched(), mock.patch.object(database, "_ban_cache", database._BanCache())):
            patcher.start()
            self.addCleanup(patcher.stop)

    def row(self, uid=UID):
        return self.db.row(uid)


# ───────────────────────────── DB: ban / unban / o'qish ─────────────────────────────
class BanUnbanTest(BanDbCase):
    def test_open_ban_with_reason_and_term(self):
        database.ban_user(UID, 60, "open", "Spam")
        info = database.get_ban_info(UID)
        self.assertEqual(set(info), {"banned", "mode", "until", "reason"})
        self.assertEqual((info["banned"], info["mode"], info["reason"]), (True, "open", "Spam"))
        self.assertAlmostEqual((info["until"] - database.get_uz_now()).total_seconds(), 3600, delta=60)
        row = self.row()
        self.assertEqual((row["is_banned"], row["ban_mode"], row["ban_reason"]), (1, "open", "Spam"))
        self.assertTrue(row["banned_at"])

    def test_silent_ban_permanent(self):
        database.ban_user(UID, None, "silent")
        info = database.get_ban_info(UID)
        self.assertEqual((info["banned"], info["mode"], info["until"], info["reason"]), (True, "silent", None, None))
        self.assertEqual(self.row()["ban_mode"], "silent")

    def test_default_mode_is_open_and_is_user_banned_follows_get_ban_info(self):
        database.ban_user(UID)
        self.assertEqual(database.get_ban_info(UID)["mode"], "open")
        banned, text = database.is_user_banned(UID)
        self.assertTrue(banned)
        self.assertIn("muddatsiz", text)
        database.ban_user(UID, 30, "silent")
        banned, text = database.is_user_banned(UID)
        self.assertTrue(banned)
        self.assertIn("gacha", text)

    def test_unban_clears_the_ban_for_both_modes_and_keeps_everything_else(self):
        premium_until = (database.get_uz_now() + dt.timedelta(days=20)).isoformat()
        for mode in ("open", "silent"):
            uid = UID + (1 if mode == "silent" else 0)
            self.db.add_user(uid, medicine_score=77, is_premium=1, premium_type="plus", premium_expires_at=premium_until)
            database.ban_user(uid, None, mode, "x")
            self.assertTrue(database.get_ban_info(uid)["banned"])
            database.unban_user(uid)
            self.assertEqual(database.get_ban_info(uid), FREE_INFO)
            row = self.row(uid)
            self.assertEqual((row["is_banned"], row["medicine_score"], row["is_premium"], row["premium_type"]),
                             (0, 77, 1, "plus"))
            self.assertEqual(row["premium_expires_at"], premium_until)            # Premium muddati o'zgarmaydi

    def test_banned_user_keeps_premium_points_and_other_data(self):
        premium_until = (database.get_uz_now() + dt.timedelta(days=9)).isoformat()
        self.db.add_user(UID, medicine_score=55, is_premium=1, premium_type="ultra", premium_expires_at=premium_until,
                         has_discount=1, spin_ai_bonus=3)
        database.ban_user(UID, 1440, "silent", "izoh")
        row = self.row()
        self.assertEqual((row["medicine_score"], row["premium_type"], row["premium_expires_at"], row["has_discount"],
                          row["spin_ai_bonus"]), (55, "ultra", premium_until, 1, 3))

    def test_rebanning_replaces_term_mode_and_reason(self):
        database.ban_user(UID, 60, "open", "Spam")
        database.ban_user(UID, None, "silent", None)
        info = database.get_ban_info(UID)
        self.assertEqual((info["mode"], info["until"], info["reason"]), ("silent", None, None))

    def test_validation_and_reason_cleanup(self):
        with self.assertRaises(ValueError):
            database.ban_user(UID, None, "loud")
        with self.assertRaises(ValueError):
            database.ban_user(UID, -5)
        with self.assertRaises(ValueError):
            database.ban_user(UID, True)
        database.ban_user(UID, None, "open", "  Qoida   buzildi \n")
        self.assertEqual(database.get_ban_info(UID)["reason"], "Qoida buzildi")
        database.ban_user(UID, None, "open", "x" * 500)
        self.assertEqual(len(database.get_ban_info(UID)["reason"]), database.BAN_REASON_MAX)
        database.ban_user(UID, None, "open", "   ")
        self.assertIsNone(database.get_ban_info(UID)["reason"])

    def test_change_duration_keeps_mode_and_reason(self):
        database.ban_user(UID, 60, "silent", "izoh")
        self.assertTrue(database.change_ban_duration(UID, 3 * 1440))
        info = database.get_ban_info(UID)
        self.assertEqual((info["mode"], info["reason"]), ("silent", "izoh"))
        self.assertAlmostEqual((info["until"] - database.get_uz_now()).total_seconds(), 3 * 86400, delta=60)
        self.assertTrue(database.change_ban_duration(UID, None))
        self.assertIsNone(database.get_ban_info(UID)["until"])
        with self.assertRaises(ValueError):
            database.change_ban_duration(UID, 0)

    def test_change_duration_refuses_a_user_who_is_not_banned(self):
        self.db.add_user(UID)
        self.assertFalse(database.change_ban_duration(UID, 60))
        self.db.add_user(UID + 1, is_banned=1, banned_until=naive_wall(minutes=-5))      # muddati o'tgan
        self.assertFalse(database.change_ban_duration(UID + 1, 60))
        self.assertFalse(database.get_ban_info(UID + 1)["banned"])


class ReadingTest(BanDbCase):
    def test_legacy_ban_without_mode_is_open(self):
        self.db.add_user(UID, is_banned=1)                                               # ban_mode NULL, muddatsiz
        info = database.get_ban_info(UID)
        self.assertEqual((info["banned"], info["mode"], info["until"], info["reason"]), (True, "open", None, None))
        self.db.add_user(UID + 1, is_banned=1, banned_until=naive_wall(minutes=30))
        info = database.get_ban_info(UID + 1)
        self.assertEqual((info["banned"], info["mode"]), (True, "open"))
        self.assertIsNotNone(info["until"])

    def test_unknown_mode_value_is_treated_as_open(self):
        self.db.add_user(UID, is_banned=1, ban_mode="weird")
        self.assertEqual(database.get_ban_info(UID)["mode"], "open")

    def test_expired_ban_reads_as_free_but_is_not_cleaned_in_the_database(self):
        self.db.add_user(UID, is_banned=1, banned_until=naive_wall(minutes=-3), ban_mode="open", ban_reason="Spam")
        self.assertEqual(database.get_ban_info(UID), FREE_INFO)
        self.assertEqual(database.is_user_banned(UID), (False, ""))
        row = self.row()
        self.assertEqual((row["is_banned"], row["ban_mode"], row["ban_reason"]), (1, "open", "Spam"))   # YOZILMAGAN
        self.assertTrue(row["banned_until"])

    def test_unknown_user_is_registered_and_free(self):
        self.assertEqual(database.get_ban_info(UID), FREE_INFO)
        self.assertIsNotNone(self.row())

    def test_returned_dict_is_a_copy(self):
        database.ban_user(UID, None, "open", "Spam")
        first = database.get_ban_info(UID)
        first["banned"] = False
        self.assertTrue(database.get_ban_info(UID)["banned"])

    def test_cache_hit_avoids_the_database_and_ban_invalidates_it(self):
        self.assertFalse(database.get_ban_info(UID)["banned"])
        with mock.patch.object(database, "_read_ban_state", side_effect=AssertionError("kesh o'tkazib yuborildi")):
            self.assertFalse(database.get_ban_info(UID)["banned"])                      # kesh
        # bazani kesh orqali emas, to'g'ridan-to'g'ri o'zgartiramiz: kesh eski qiymatni beradi
        import sqlite3
        con = sqlite3.connect(self.db.path)
        con.execute("UPDATE users SET is_banned = 1, ban_mode = 'silent' WHERE user_id = ?", (UID,))
        con.commit()
        con.close()
        self.assertFalse(database.get_ban_info(UID)["banned"])
        database.ban_user(UID, None, "open", "Spam")                                    # invalidatsiya
        self.assertEqual(database.get_ban_info(UID)["mode"], "open")
        database.unban_user(UID)
        self.assertFalse(database.get_ban_info(UID)["banned"])

    def test_change_duration_invalidates_the_cache(self):
        database.ban_user(UID, 10, "open")
        old_until = database.get_ban_info(UID)["until"]
        database.change_ban_duration(UID, 1000)
        self.assertGreater(database.get_ban_info(UID)["until"], old_until + dt.timedelta(hours=1))

    def test_cache_ttl_never_outlives_the_ban(self):
        self.db.add_user(UID, is_banned=1, banned_until=naive_wall(seconds=3), ban_mode="open")
        info, ttl = database._read_ban_state(UID)
        self.assertTrue(info["banned"])
        self.assertLessEqual(ttl, 3.0)


class SqlConditionTest(BanDbCase):
    """Yagona "hozir banda emas" sharti: muddati o'tgan, lekin hali tozalanmagan ban chiqarib tashlanmaydi."""

    def setUp(self):
        super().setUp()
        self.db.add_user(1, full_name="free")
        self.db.add_user(2, full_name="open", is_banned=1, ban_mode="open")
        self.db.add_user(3, full_name="silent", is_banned=1, ban_mode="silent", banned_until=naive_wall(hours=5))
        self.db.add_user(4, full_name="expired", is_banned=1, ban_mode="open", banned_until=naive_wall(minutes=-1))
        self.db.add_user(5, full_name="legacy", is_banned=1)                              # ban_mode NULL

    def test_active_user_ids_exclude_active_bans_but_include_expired_uncleaned(self):
        self.assertEqual(sorted(database.get_active_user_ids()), [1, 4])

    def test_broadcast_targets_and_banned_count(self):
        targets = database.get_broadcast_targets()
        self.assertEqual((sorted(targets["users"]), targets["banned"]), ([1, 4], 3))
        self.assertEqual(database.get_banned_count(), 3)

    def test_the_two_conditions_are_exact_complements(self):
        import sqlite3
        con = sqlite3.connect(self.db.path)
        params = database.not_banned_params()
        ok = {r[0] for r in con.execute("SELECT user_id FROM users WHERE " + database.NOT_BANNED_SQL.replace("%s", "?"), params)}
        banned = {r[0] for r in con.execute("SELECT user_id FROM users WHERE " + database.BANNED_SQL.replace("%s", "?"), params)}
        con.close()
        self.assertEqual(ok | banned, {1, 2, 3, 4, 5})
        self.assertEqual(ok & banned, set())

    def test_daily_tips_subscribers_skip_banned_users(self):
        import sqlite3
        con = sqlite3.connect(self.db.path)
        con.execute("UPDATE users SET daily_tips_subscribed = 1")
        con.commit()
        con.close()
        self.assertEqual(sorted(database.get_daily_tips_subscribers()), [1, 4])

    def test_premium_checkin_targets_skip_banned_users(self):
        import sqlite3
        con = sqlite3.connect(self.db.path)
        con.execute("UPDATE users SET is_premium = 1, premium_type = 'pro'")
        con.commit()
        con.close()
        self.assertEqual(sorted(r[0] for r in database.get_premium_checkin_targets()), [1, 4])

    def test_active_reminders_skip_banned_users(self):
        import sqlite3
        con = sqlite3.connect(self.db.path)
        con.execute("CREATE TABLE reminders (id INTEGER PRIMARY KEY, user_id INTEGER, medicine_name TEXT, times TEXT, "
                    "days TEXT, is_active INTEGER)")
        for i, uid in enumerate((1, 2, 3, 4, 5), 1):
            con.execute("INSERT INTO reminders VALUES (?, ?, 'Dori', '08:00', 'daily', 1)", (i, uid))
        con.commit()
        con.close()
        self.assertEqual(sorted(r[1] for r in database.get_all_active_reminders()), [1, 4])

    def test_admin_listing_counts_only_current_bans(self):
        data = database.admin_users_page(0, 10, banned_only=True)
        self.assertEqual((data["total"], data["banned_count"], data["listed"]), (5, 3, 3))
        self.assertEqual(sorted(u["user_id"] for u in data["users"]), [2, 3, 5])
        everyone = database.admin_users_page(0, 10)
        self.assertEqual(everyone["listed"], 5)
        record = {u["user_id"]: u for u in everyone["users"]}
        self.assertEqual(record[3]["ban"]["mode"], "silent")
        self.assertFalse(record[4]["ban"]["banned"])                                      # muddati o'tgan — "yo'q"
        self.assertEqual(record[5]["ban"]["mode"], "open")                                # eski ban = ochiq


class ExpireFinishedBansTest(BanDbCase):
    def test_clears_expired_bans_and_returns_the_modes(self):
        self.db.add_user(1, is_banned=1, ban_mode="open", banned_until=naive_wall(minutes=-2), ban_reason="Spam")
        self.db.add_user(2, is_banned=1, ban_mode="silent", banned_until=naive_wall(minutes=-2))
        self.db.add_user(3, is_banned=1, banned_until=naive_wall(minutes=-2))            # eski ban (mode NULL)
        self.db.add_user(4, is_banned=1, ban_mode="open", banned_until=naive_wall(hours=2))
        self.db.add_user(5, is_banned=1, ban_mode="open")                                 # muddatsiz
        self.db.add_user(6)
        result = database.expire_finished_bans()
        self.assertEqual(sorted(result), [(1, "open"), (2, "silent"), (3, "open")])
        for uid in (1, 2, 3):
            self.assertEqual(self.row(uid)["is_banned"], 0)
        for uid in (4, 5):
            self.assertEqual(self.row(uid)["is_banned"], 1)
        self.assertEqual(database.expire_finished_bans(), [])                             # ikkinchi chaqiruv: hech narsa

    def test_premium_and_points_untouched(self):
        premium_until = (database.get_uz_now() + dt.timedelta(days=4)).isoformat()
        self.db.add_user(1, is_banned=1, ban_mode="open", banned_until=naive_wall(minutes=-2), medicine_score=9,
                         is_premium=1, premium_type="pro", premium_expires_at=premium_until)
        database.expire_finished_bans()
        row = self.row(1)
        self.assertEqual((row["medicine_score"], row["premium_type"], row["premium_expires_at"]), (9, "pro", premium_until))

    def test_invalidates_the_cache(self):
        self.db.add_user(1, is_banned=1, ban_mode="open", banned_until=naive_wall(seconds=-1))
        database._ban_cache.put(1, dict(OPEN_INFO), 30, database._ban_cache.epoch())       # eskirgan kesh
        database.expire_finished_bans()
        self.assertIsNone(database._ban_cache.get(1))

    def test_parallel_calls_split_the_users_exactly_once(self):
        for uid in range(1, 41):
            self.db.add_user(uid, is_banned=1, ban_mode="open", banned_until=naive_wall(minutes=-1))
        with ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(lambda _: database.expire_finished_bans(), range(10)))
        claimed = [uid for result in results for uid, _mode in result]
        self.assertEqual(sorted(claimed), list(range(1, 41)))                              # har user aynan bir marta


# ───────────────────────────── BanMiddleware ─────────────────────────────
def message_event():
    event = mock.MagicMock(spec=types.Message)
    event.answer = mock.AsyncMock()
    event.successful_payment = None
    event.text = "salom"
    return event


def callback_event():
    event = mock.MagicMock(spec=types.CallbackQuery)
    event.answer = mock.AsyncMock()
    return event


def middleware_chain(dispatcher, kind):
    return list(getattr(dispatcher, kind).outer_middleware)            # MiddlewareManager — ketma-ketlik (birinchisi eng tashqi)


async def run_chain(middlewares, event, handler, user_id=UID):
    async def call(index, current, data):
        if index == len(middlewares):
            return await handler(current, data)
        return await middlewares[index](lambda e, d: call(index + 1, e, d), current, data)
    return await call(0, event, {"event_from_user": SimpleNamespace(id=user_id)})


class MiddlewareBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.dp = Dispatcher()
        bot_mod.setup_middlewares(self.dp)
        self.calls = 0

        async def handler(event, data):
            self.calls += 1
            return "handled"

        self.handler = handler
        self.info = dict(FREE_INFO)
        patcher = mock.patch.object(database, "get_ban_info", side_effect=lambda uid: dict(self.info))
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(bot_mod, "ADMIN_USERNAME", "adminbot")
        patcher.start()
        self.addCleanup(patcher.stop)

    async def message(self, user_id=UID, event=None):
        event = event or message_event()
        result = await run_chain(middleware_chain(self.dp, "message"), event, self.handler, user_id)
        return event, result

    async def callback(self, user_id=UID, event=None):
        event = event or callback_event()
        result = await run_chain(middleware_chain(self.dp, "callback_query"), event, self.handler, user_id)
        return event, result


class MiddlewareOrderTest(MiddlewareBase):
    def test_ban_comes_before_throttling_and_answer_callback(self):
        names = [type(m).__name__ for m in middleware_chain(self.dp, "message")]
        self.assertEqual(names, ["BanMiddleware", "ThrottlingMiddleware", "FsmResetMiddleware"])
        names = [type(m).__name__ for m in middleware_chain(self.dp, "callback_query")]
        self.assertEqual(names, ["BanMiddleware", "ThrottlingMiddleware", "AnswerCallbackMiddleware"])

    def test_main_uses_the_shared_setup(self):
        with open(os.path.join(PROJECT_DIR, "bot.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn("setup_middlewares(dp)", src)
        self.assertNotIn("dp.message.outer_middleware(ThrottlingMiddleware())\n    dp.callback_query.outer_middleware(ThrottlingMiddleware())"
                         "\n    dp.message.outer_middleware(BanMiddleware())", src)


class OpenBanMiddlewareTest(MiddlewareBase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.info = {"banned": True, "mode": "open", "reason": "Spam",
                     "until": dt.datetime(2026, 11, 20, 14, 0, tzinfo=UZ)}

    async def test_message_gets_the_ban_text_with_term_reason_and_admin(self):
        event, result = await self.message()
        self.assertIsNone(result)
        self.assertEqual(self.calls, 0)                                                   # handler chaqirilmaydi
        event.answer.assert_awaited_once()
        text = event.answer.await_args.args[0]
        self.assertIn("Siz bloklangansiz.", text)
        self.assertIn("20.11.2026 14:00 gacha", text)
        self.assertIn("Sabab: Spam", text)
        self.assertIn("Murojaat uchun: @adminbot", text)
        self.assertEqual(event.answer.await_args.kwargs["parse_mode"], "HTML")

    async def test_permanent_ban_says_muddatsiz_and_no_reason_line(self):
        self.info = {"banned": True, "mode": "open", "reason": None, "until": None}
        event, _ = await self.message()
        text = event.answer.await_args.args[0]
        self.assertIn("♾ muddatsiz", text)
        self.assertNotIn("Sabab", text)

    async def test_callback_gets_a_short_alert(self):
        event, result = await self.callback()
        self.assertIsNone(result)
        self.assertEqual(self.calls, 0)
        event.answer.assert_awaited_once()
        text = event.answer.await_args.args[0]
        self.assertTrue(event.answer.await_args.kwargs["show_alert"])
        self.assertIn("Siz bloklangansiz", text)
        self.assertIn("20.11.2026 14:00", text)
        self.assertIn("Sabab: Spam", text)
        self.assertLessEqual(len(text), 200)                                              # Telegram alert chegarasi

    async def test_alert_with_a_very_long_reason_is_trimmed_to_200_chars(self):
        self.info["reason"] = "x" * 200
        event, _ = await self.callback()
        self.assertLessEqual(len(event.answer.await_args.args[0]), 200)

    async def test_every_message_is_answered_and_throttling_never_speaks(self):
        """Tez yozsa ham HAR safar ban matni (throttling ogohlantirishi emas)."""
        events = [message_event() for _ in range(5)]
        for event in events:
            await self.message(event=event)
        for event in events:
            event.answer.assert_awaited_once()
            self.assertIn("Siz bloklangansiz", event.answer.await_args.args[0])
            self.assertNotIn("shoshilmang", event.answer.await_args.args[0])
        self.assertEqual(self.calls, 0)

    async def test_html_in_reason_is_escaped(self):
        self.info["reason"] = '<b>x</b><a href="http://e">'
        event, _ = await self.message()
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", event.answer.await_args.args[0])
        self.assertNotIn('<a href="http://e">', event.answer.await_args.args[0])

    async def test_answer_failure_is_logged_not_raised(self):
        event = message_event()
        event.answer = mock.AsyncMock(side_effect=RuntimeError("user botni bloklagan"))
        with self.assertLogs(level="WARNING"):
            _, result = await self.message(event=event)
        self.assertIsNone(result)


class SilentBanMiddlewareTest(MiddlewareBase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.info = dict(SILENT_INFO, until=dt.datetime(2026, 11, 20, 14, 0, tzinfo=UZ), reason="admin izohi")

    async def test_message_gets_no_answer_at_all(self):
        event, result = await self.message()
        self.assertIsNone(result)
        self.assertEqual(self.calls, 0)
        self.assertEqual(event.method_calls, [])                                          # hech qanday metod chaqirilmadi
        event.answer.assert_not_awaited()

    async def test_callback_is_not_answered_either(self):
        event, result = await self.callback()
        self.assertIsNone(result)
        self.assertEqual(self.calls, 0)
        self.assertEqual(event.method_calls, [])
        event.answer.assert_not_awaited()                                                  # "yuklanmoqda" bo'lib qolaveradi

    async def test_rapid_fire_never_triggers_a_throttling_warning(self):
        events = [message_event() for _ in range(8)] + [callback_event() for _ in range(8)]
        for event in events:
            if isinstance(event, types.CallbackQuery):
                await self.callback(event=event)
            else:
                await self.message(event=event)
        for event in events:
            self.assertEqual(event.method_calls, [])
            event.answer.assert_not_awaited()
        self.assertEqual(self.calls, 0)

    async def test_answer_callback_middleware_stays_silent_too(self):
        chain = middleware_chain(self.dp, "callback_query")
        answer_mw = next(m for m in chain if type(m).__name__ == "AnswerCallbackMiddleware")
        event = callback_event()
        ban = next(m for m in chain if type(m).__name__ == "BanMiddleware")
        await ban(lambda e, d: answer_mw(self.handler, e, d), event, {"event_from_user": SimpleNamespace(id=UID)})
        event.answer.assert_not_awaited()
        self.assertEqual(self.calls, 0)

    async def test_user_who_is_not_banned_still_gets_the_normal_flow_and_throttling(self):
        self.info = dict(FREE_INFO)
        first, result = await self.message(user_id=UID + 50)
        self.assertEqual(result, "handled")
        second, result = await self.message(user_id=UID + 50)                              # darhol ikkinchisi — throttling
        self.assertIsNone(result)
        second.answer.assert_awaited_once()
        self.assertIn("shoshilmang", second.answer.await_args.args[0])
        self.assertEqual(self.calls, 1)

    async def test_banned_flooding_does_not_throttle_a_different_user(self):
        for _ in range(3):
            await self.message(user_id=UID)
        self.info = dict(FREE_INFO)
        event, result = await self.message(user_id=UID + 1)
        self.assertEqual(result, "handled")


class PaymentMessageThroughBanTest(MiddlewareBase):
    async def test_successful_payment_is_not_swallowed_by_the_ban(self):
        """Pul xavfsizligi: Telegram allaqachon yechgan to'lov yo'qolmasin — ban shundan keyin qo'yilgan bo'lishi mumkin."""
        for offset, info in enumerate((dict(OPEN_INFO), dict(SILENT_INFO))):
            self.info = info
            self.calls = 0
            event = message_event()
            event.successful_payment = SimpleNamespace(invoice_payload="PRO_7_DAYS")
            _, result = await self.message(user_id=UID + 100 + offset, event=event)       # throttling aralashmasin
            self.assertEqual(result, "handled")
            self.assertEqual(self.calls, 1)

    async def test_ordinary_messages_are_still_blocked(self):
        self.info = dict(SILENT_INFO)
        _, result = await self.message()
        self.assertIsNone(result)
        self.assertEqual(self.calls, 0)


class DbErrorTest(MiddlewareBase):
    async def test_database_failure_is_fail_closed(self):
        with mock.patch.object(database, "get_ban_info", side_effect=ConnectionError("db down")):
            with self.assertLogs(level="ERROR"):
                event, result = await self.message()
        self.assertIsNone(result)
        self.assertEqual(self.calls, 0)


# ───────────────────────────── pre_checkout ─────────────────────────────
class PreCheckoutBanTest(unittest.IsolatedAsyncioTestCase):
    async def run_pre_checkout(self, info):
        query = mock.MagicMock()
        query.from_user = SimpleNamespace(id=UID)
        query.invoice_payload = "PRO_7_DAYS"
        query.currency = "XTR"
        query.total_amount = 50
        query.answer = mock.AsyncMock()
        with mock.patch.object(database, "get_ban_info", return_value=info), \
                mock.patch.object(database, "get_premium_view", return_value=database.admin_premium_view(0, None, None)), \
                mock.patch.dict(os.environ, {"PRO_TRIAL_STARS": "50"}):
            await bot_mod.process_pre_checkout(query)
        return query.answer.await_args.kwargs

    async def test_open_ban_rejects_the_payment_with_the_reason(self):
        kwargs = await self.run_pre_checkout(dict(OPEN_INFO, reason="Spam"))
        self.assertFalse(kwargs["ok"])
        self.assertIn("bloklanganligi sababli", kwargs["error_message"])
        self.assertIn("Spam", kwargs["error_message"])

    async def test_silent_ban_rejects_with_a_generic_error_and_no_hint(self):
        kwargs = await self.run_pre_checkout(dict(SILENT_INFO, reason="admin izohi"))
        self.assertFalse(kwargs["ok"])
        self.assertEqual(kwargs["error_message"], "Xatolik yuz berdi. Keyinroq urinib ko'ring.")
        for word in ("ban", "blok", "izoh"):
            self.assertNotIn(word, kwargs["error_message"].lower())

    async def test_free_user_still_pays(self):
        self.assertTrue((await self.run_pre_checkout(dict(FREE_INFO)))["ok"])


# ───────────────────────────── API ─────────────────────────────
class BanApiTest(ApiTestBase):
    PATHS = ("/api/state", "/api/spin/claim", "/api/bonus/claim", "/api/points/redeem", "/api/invoice")

    async def asyncSetUp(self):
        await super().asyncSetUp()
        patcher = mock.patch.object(bot_mod, "ADMIN_USERNAME", "adminbot")
        patcher.start()
        self.addCleanup(patcher.stop)

    def ban(self, info):
        patcher = mock.patch.object(database, "get_ban_info", side_effect=lambda uid: dict(info))
        patcher.start()
        self.addCleanup(patcher.stop)

    def untouched(self):
        for name in ("spin", "daily", "score", "view", "bonus_info", "prize", "ai_quota"):
            self.m[name].assert_not_called()

    async def post_to(self, path):
        extra = {"plan": "buy_pro_7"} if path == "/api/invoice" else None
        return await self.post(path, extra=extra)

    async def test_open_ban_gives_403_banned_with_term_reason_and_contact(self):
        until = dt.datetime(2026, 11, 20, 14, 0, tzinfo=UZ)
        self.ban({"banned": True, "mode": "open", "until": until, "reason": "Spam"})
        for path in self.PATHS:
            with self.subTest(path=path):
                resp, data = await self.post_to(path)
                self.assertEqual(resp.status, 403)
                self.assertEqual(data, {"ok": False, "error": "banned", "until": "2026-11-20T14:00:00+05:00",
                                        "reason": "Spam", "contact": "@adminbot"})
        self.untouched()

    async def test_open_permanent_ban_without_reason(self):
        self.ban(dict(OPEN_INFO))
        resp, data = await self.post("/api/state")
        self.assertEqual((resp.status, data["error"], data["until"], data["reason"]), (403, "banned", None, None))

    async def test_contact_is_null_when_admin_username_is_not_configured(self):
        self.ban(dict(OPEN_INFO))
        with mock.patch.object(bot_mod, "ADMIN_USERNAME", "YOUR_ADMIN_USERNAME"):
            _, data = await self.post("/api/state")
        self.assertIsNone(data["contact"])

    async def test_silent_ban_looks_exactly_like_a_plain_server_error(self):
        self.ban(dict(SILENT_INFO, reason="admin izohi", until=dt.datetime(2026, 11, 20, 14, 0, tzinfo=UZ)))
        silent = {}
        for path in self.PATHS:
            resp, data = await self.post_to(path)
            silent[path] = (resp.status, data, resp.headers.get("Content-Type"), resp.headers.get("Retry-After"))
        self.untouched()
        # Haqiqiy server xatosi (action ichida kutilmagan istisno) — bir xil status, tana va sarlavhalar
        with mock.patch.object(database, "get_ban_info", return_value=dict(FREE_INFO)), \
                mock.patch.object(bot_mod, "_api_state_action", side_effect=RuntimeError("boom")):
            resp, data = await self.post("/api/state")
        real = (resp.status, data, resp.headers.get("Content-Type"), resp.headers.get("Retry-After"))
        for path, got in silent.items():
            with self.subTest(path=path):
                self.assertEqual(got, real)
        self.assertEqual(real[0:2], (500, {"ok": False, "error": "server_error"}))

    async def test_silent_ban_response_never_mentions_the_ban(self):
        self.ban(dict(SILENT_INFO, reason="Spam", until=dt.datetime(2026, 11, 20, 14, 0, tzinfo=UZ)))
        for path in self.PATHS + ("/api/ai/chat",):
            resp, _ = await self.post_to(path)
            body = (await resp.text()).lower()
            for word in ("ban", "blok", "spam", "2026", "adminbot", "until", "reason", "contact"):
                self.assertNotIn(word, body, (path, word))

    async def test_ai_chat_open_ban_matches_the_other_endpoints(self):
        until = dt.datetime(2026, 11, 20, 14, 0, tzinfo=UZ)
        self.ban({"banned": True, "mode": "open", "until": until, "reason": "Spam"})
        resp, data = await self.post("/api/ai/chat", extra={"message": "salom"})
        self.assertEqual(resp.status, 403)
        self.assertEqual(data, {"ok": False, "error": "banned", "until": "2026-11-20T14:00:00+05:00", "reason": "Spam",
                                "contact": "@adminbot"})

    async def test_ai_chat_silent_ban_equals_the_endpoints_real_server_error(self):
        self.ban(dict(SILENT_INFO))
        resp, silent = await self.post("/api/ai/chat", extra={"message": "salom"})
        silent_status = resp.status
        with mock.patch.object(database, "get_ban_info", return_value=dict(FREE_INFO)), \
                mock.patch.object(database, "try_consume_free_ai", side_effect=RuntimeError("boom")):
            resp, real = await self.post("/api/ai/chat", extra={"message": "salom"})
        self.assertEqual((silent_status, silent), (resp.status, real))
        self.assertEqual(silent["error"], "server")

    async def test_ai_chat_banned_user_consumes_no_quota_and_calls_no_ai(self):
        self.ban(dict(OPEN_INFO))
        with mock.patch.object(bot_mod, "get_gemini_response", mock.AsyncMock()) as ai, \
                mock.patch.object(database, "try_consume_free_ai") as consume:
            await self.post("/api/ai/chat", extra={"message": "salom"})
        ai.assert_not_awaited()
        consume.assert_not_called()

    async def test_invoice_is_closed_to_banned_users(self):
        for info in (dict(OPEN_INFO), dict(SILENT_INFO)):
            self.ban(info)
            create = mock.AsyncMock(return_value="https://t.me/$x")
            with mock.patch.object(bot_mod, "bot", SimpleNamespace(create_invoice_link=create)):
                resp, data = await self.post("/api/invoice", extra={"plan": "buy_pro_7"})
            self.assertNotEqual(resp.status, 200)
            create.assert_not_awaited()

    async def test_expired_ban_does_not_block_the_api(self):
        self.ban(dict(FREE_INFO))
        resp, data = await self.post("/api/state")
        self.assertEqual((resp.status, data["ok"]), (200, True))

    async def test_database_error_in_the_ban_check_is_a_plain_server_error(self):
        with mock.patch.object(database, "get_ban_info", side_effect=ConnectionError("db")):
            resp, data = await self.post("/api/state")
        self.assertEqual((resp.status, data), (500, {"ok": False, "error": "server_error"}))


# ───────────────────────────── fon vazifasi ─────────────────────────────
class BanExpiryJobTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = SqliteDB()
        self.addCleanup(self.db.close)
        self.fake_bot = mock.MagicMock()
        self.fake_bot.send_message = mock.AsyncMock()
        for patcher in (self.db.patched(), mock.patch.object(bot_mod, "bot", self.fake_bot),
                        mock.patch.object(bot_mod, "BAN_EXPIRY_SEND_PAUSE", 0),
                        mock.patch.object(database, "_ban_cache", database._BanCache())):
            patcher.start()
            self.addCleanup(patcher.stop)

    def add(self, uid, mode, **cols):
        self.db.add_user(uid, is_banned=1, ban_mode=mode, banned_until=naive_wall(minutes=-5), **cols)

    def sent_to(self):
        return [c.args[0] for c in self.fake_bot.send_message.await_args_list]

    async def test_open_ban_gets_one_message_and_silent_gets_none(self):
        self.add(1, "open")
        self.add(2, "silent")
        self.add(3, None)                                                                 # eski ban = ochiq
        stats = await bot_mod.run_ban_expiry_check()
        self.assertEqual(stats, {"cleared": 3, "notified": 2, "failed": 0})
        self.assertEqual(sorted(self.sent_to()), [1, 3])
        for call in self.fake_bot.send_message.await_args_list:
            self.assertEqual(call.args[1], "✅ Blok muddati tugadi. Botdan yana foydalanishingiz mumkin.")
        for uid in (1, 2, 3):
            self.assertEqual(self.db.row(uid)["is_banned"], 0)

    async def test_two_parallel_runs_send_the_message_once(self):
        self.add(1, "open")
        results = await asyncio.gather(bot_mod.run_ban_expiry_check(), bot_mod.run_ban_expiry_check(),
                                       bot_mod.run_ban_expiry_check())
        self.assertEqual(self.sent_to(), [1])
        self.assertEqual(sum(r["cleared"] for r in results), 1)

    async def test_two_runs_in_separate_threads_of_the_database_layer_split_the_work(self):
        for uid in range(1, 21):
            self.add(uid, "open")
        first, second = await asyncio.gather(asyncio.to_thread(database.expire_finished_bans),
                                             asyncio.to_thread(database.expire_finished_bans))
        self.assertEqual(sorted(uid for uid, _ in first + second), list(range(1, 21)))

    async def test_second_run_is_a_no_op(self):
        self.add(1, "open")
        await bot_mod.run_ban_expiry_check()
        self.fake_bot.send_message.reset_mock()
        self.assertEqual(await bot_mod.run_ban_expiry_check(), {"cleared": 0, "notified": 0, "failed": 0})
        self.fake_bot.send_message.assert_not_awaited()

    async def test_active_bans_are_left_alone(self):
        self.db.add_user(1, is_banned=1, ban_mode="open", banned_until=naive_wall(hours=3))
        self.db.add_user(2, is_banned=1, ban_mode="open")
        await bot_mod.run_ban_expiry_check()
        self.fake_bot.send_message.assert_not_awaited()
        self.assertEqual((self.db.row(1)["is_banned"], self.db.row(2)["is_banned"]), (1, 1))

    async def test_blocked_user_is_logged_and_the_job_goes_on(self):
        self.add(1, "open")
        self.add(2, "open")
        self.fake_bot.send_message = mock.AsyncMock(side_effect=[RuntimeError("Forbidden: bot was blocked"), None])
        with self.assertLogs(level="WARNING"):
            stats = await bot_mod.run_ban_expiry_check()
        self.assertEqual((stats["cleared"], stats["notified"], stats["failed"]), (2, 1, 1))

    async def test_premium_and_points_survive_the_cleanup(self):
        premium_until = (database.get_uz_now() + dt.timedelta(days=12)).isoformat()
        self.add(1, "open", medicine_score=42, is_premium=1, premium_type="ultra", premium_expires_at=premium_until)
        await bot_mod.run_ban_expiry_check()
        row = self.db.row(1)
        self.assertEqual((row["medicine_score"], row["premium_type"], row["premium_expires_at"]), (42, "ultra", premium_until))

    async def test_cache_is_invalidated_so_the_user_can_use_the_bot_at_once(self):
        self.add(1, "open")
        database._ban_cache.put(1, dict(OPEN_INFO), 30, database._ban_cache.epoch())
        await bot_mod.run_ban_expiry_check()
        self.assertFalse(database.get_ban_info(1)["banned"])

    async def test_loop_survives_errors_and_is_started_in_main(self):
        runs = []

        async def fake_check(now=None):
            runs.append(1)
            if len(runs) == 1:
                raise RuntimeError("boom")
            return {}

        sleeps = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps) >= 2:
                raise asyncio.CancelledError

        with mock.patch.object(bot_mod, "run_ban_expiry_check", fake_check), \
                mock.patch.object(bot_mod.asyncio, "sleep", fake_sleep):
            with self.assertLogs(level="ERROR"):
                with self.assertRaises(asyncio.CancelledError):
                    await bot_mod.ban_expiry_loop()
        self.assertEqual(len(runs), 2)                                                    # xatodan keyin ham davom etdi
        self.assertEqual(sleeps, [bot_mod.BAN_EXPIRY_CHECK_INTERVAL] * 2)
        self.assertLessEqual(bot_mod.BAN_EXPIRY_CHECK_INTERVAL, 300)                       # har 1-5 daqiqada
        with open(os.path.join(PROJECT_DIR, "bot.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn("asyncio.create_task(ban_expiry_loop())", src)


# ───────────────────────────── yordamchilar ─────────────────────────────
class HelpersTest(unittest.IsolatedAsyncioTestCase):
    async def test_user_is_banned_helper(self):
        for info, expected in ((OPEN_INFO, True), (SILENT_INFO, True), (FREE_INFO, False)):
            with mock.patch.object(database, "get_ban_info", return_value=dict(info)):
                self.assertEqual(await bot_mod.user_is_banned(UID), expected)

    async def test_user_is_banned_fails_closed_on_a_database_error(self):
        with mock.patch.object(database, "get_ban_info", side_effect=ConnectionError("db")):
            with self.assertLogs(level="WARNING"):
                self.assertTrue(await bot_mod.user_is_banned(UID))

    def test_user_texts(self):
        until = dt.datetime(2026, 11, 20, 14, 0, tzinfo=UZ)
        info = {"banned": True, "mode": "open", "until": until, "reason": "Spam"}
        with mock.patch.object(bot_mod, "ADMIN_USERNAME", "adminbot"):
            self.assertEqual(
                bot_mod.ban_user_notification(info),
                "🚫 <b>Siz botdan foydalanishdan chetlashtirildingiz.</b>\n⏳ Muddat: 20.11.2026 14:00 gacha\n"
                "📝 Sabab: Spam\n\nMurojaat uchun: @adminbot")
            forever = bot_mod.ban_user_notification(dict(info, until=None, reason=None))
            self.assertIn("⏳ Muddat: ♾ muddatsiz", forever)
            self.assertNotIn("Sabab", forever)
        self.assertEqual(bot_mod.BAN_LIFTED_TEXT, "✅ Siz blokdan chiqarildingiz. Botdan yana foydalanishingiz mumkin.")
        self.assertEqual(bot_mod.BAN_EXPIRED_TEXT, "✅ Blok muddati tugadi. Botdan yana foydalanishingiz mumkin.")


if __name__ == "__main__":
    unittest.main()
