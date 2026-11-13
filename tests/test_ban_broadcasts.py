"""
test_ban_broadcasts.py — banlangan userga (IKKALA rejim) hech qanday avtomatik / ommaviy xabar bormaydi.

Tekshiriladigan yuborish joylari: admin /broadcast (hisobotda "🚫 Banlangan (o'tkazib yuborildi): N"), kunlik maslahatlar,
dori eslatmalari, 08:00 / 10:10 / 20:30 (Premium check-in) engagement, Premium tugash eslatmasi, referal xabari, Premium paneli.
Hammasi yagona "hozir banda emas" sharti (database.NOT_BANNED_SQL): muddati o'tgan, lekin hali tozalanmagan ban QO'SHILADI.
DB — HAQIQIY SQL (tests/sqlite_db.py); Telegram soxta.
"""
import asyncio
import datetime as dt
import importlib
import inspect
import os
import sqlite3
import sys
import types as pytypes
import unittest
from types import SimpleNamespace
from unittest import mock

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("BOT_TOKEN", "123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567890")
os.environ.setdefault("GEMINI_API_KEY", "test_gemini_key")

import bot as bot_mod  # noqa: E402
import database  # noqa: E402
from services import engagement  # noqa: E402
from tests.sqlite_db import SqliteDB  # noqa: E402

ADMIN = 111_000_111
UZ = dt.timezone(dt.timedelta(hours=5))
FREE, OPEN, SILENT, EXPIRED, LEGACY = 1, 2, 3, 4, 5
EXPECTED = [FREE, EXPIRED]                       # banda bo'lmaganlar (muddati o'tgan, tozalanmagan ban — ham)


def wall(**delta):
    return (database.get_uz_now() + dt.timedelta(**delta)).replace(tzinfo=None).isoformat()


class Sent:
    """Soxta bot: yuborilgan xabarlarning qabul qiluvchilari."""

    def __init__(self):
        self.send_message = mock.AsyncMock(side_effect=self._send)
        self.copy_message = mock.AsyncMock()
        self.set_chat_menu_button = mock.AsyncMock()
        self.get_chat = mock.AsyncMock()

    async def _send(self, chat_id=None, text=None, *args, **kwargs):
        return SimpleNamespace(message_id=1)

    def recipients(self):
        ids = []
        for call in self.send_message.await_args_list:
            ids.append(call.kwargs["chat_id"] if "chat_id" in call.kwargs else call.args[0])
        for call in self.copy_message.await_args_list:
            ids.append(call.kwargs["chat_id"])
        return sorted(ids)


class BanFixture(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = SqliteDB()
        self.addCleanup(self.db.close)
        self.fake_bot = Sent()
        for patcher in (self.db.patched(), mock.patch.object(bot_mod, "bot", self.fake_bot),
                        mock.patch.object(bot_mod, "ADMIN_ID", ADMIN),
                        mock.patch.object(database, "_ban_cache", database._BanCache()),
                        mock.patch.object(bot_mod, "PREMIUM_EXPIRY_SEND_PAUSE", 0)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.db.add_user(FREE, full_name="Erkin")
        self.db.add_user(OPEN, full_name="Ochiq", is_banned=1, ban_mode="open")
        self.db.add_user(SILENT, full_name="Sirli", is_banned=1, ban_mode="silent", banned_until=wall(days=3))
        self.db.add_user(EXPIRED, full_name="Tugagan", is_banned=1, ban_mode="open", banned_until=wall(minutes=-5))
        self.db.add_user(LEGACY, full_name="Eski", is_banned=1)                           # ban_mode NULL = ochiq

    def sql(self, statement, params=()):
        con = sqlite3.connect(self.db.path)
        con.execute(statement, params)
        con.commit()
        con.close()


# ───────────────────────────── admin /broadcast ─────────────────────────────
class BroadcastTest(BanFixture):
    async def run_broadcast(self, data):
        state = mock.MagicMock()
        state.get_data = mock.AsyncMock(return_value=data)
        state.clear = mock.AsyncMock()
        progress = mock.MagicMock()
        progress.edit_text = mock.AsyncMock()
        callback = mock.MagicMock()
        callback.data = "broadcast_confirm"
        callback.from_user.id = ADMIN
        callback.message.chat.id = ADMIN
        callback.message.edit_text = mock.AsyncMock(return_value=progress)
        with mock.patch.object(bot_mod.asyncio, "sleep", mock.AsyncMock()):
            await bot_mod.process_broadcast_confirmation(callback, state)
        return progress.edit_text.await_args.args[0]

    async def test_text_broadcast_skips_banned_users_and_reports_them(self):
        report = await self.run_broadcast({"broadcast_text": "Salom hammaga"})
        self.assertEqual(self.fake_bot.recipients(), EXPECTED)
        self.assertIn("🚫 Banlangan (o'tkazib yuborildi): 3", report)
        self.assertIn("Jami: 2", report)
        self.assertIn("Muvaffaqiyatli: 2", report)

    async def test_copied_message_broadcast_skips_banned_users_too(self):
        report = await self.run_broadcast({"broadcast_msg_id": 77})
        self.assertEqual(self.fake_bot.recipients(), EXPECTED)
        self.assertIn("🚫 Banlangan (o'tkazib yuborildi): 3", report)

    async def test_when_nobody_is_banned_the_line_says_zero(self):
        self.sql("UPDATE users SET is_banned = 0")
        report = await self.run_broadcast({"broadcast_text": "x"})
        self.assertEqual(self.fake_bot.recipients(), [1, 2, 3, 4, 5])
        self.assertIn("🚫 Banlangan (o'tkazib yuborildi): 0", report)

    async def test_expired_but_uncleaned_users_are_included(self):
        await self.run_broadcast({"broadcast_text": "x"})
        self.assertIn(EXPIRED, self.fake_bot.recipients())
        self.assertNotIn(LEGACY, self.fake_bot.recipients())


# ───────────────────────────── kunlik maslahatlar va dori eslatmalari ─────────────────────────────
class TipsAndRemindersTest(BanFixture):
    async def test_daily_tips_go_only_to_users_who_are_not_banned(self):
        self.sql("UPDATE users SET daily_tips_subscribed = 1")
        with mock.patch.object(bot_mod, "get_gemini_response", mock.AsyncMock(return_value="Maslahat")), \
                mock.patch.object(bot_mod.asyncio, "sleep", mock.AsyncMock()):
            await bot_mod.send_daily_tips()
        self.assertEqual(self.fake_bot.recipients(), EXPECTED)

    async def test_medicine_reminders_skip_banned_users(self):
        self.sql("CREATE TABLE reminders (id INTEGER PRIMARY KEY, user_id INTEGER, medicine_name TEXT, times TEXT, "
                 "days TEXT, is_active INTEGER)")
        for i, uid in enumerate((FREE, OPEN, SILENT, EXPIRED, LEGACY), 1):
            self.sql("INSERT INTO reminders VALUES (?, ?, 'Dori', '08:00', 'daily', 1)", (i, uid))
        now = dt.datetime(2026, 11, 14, 8, 0, tzinfo=UZ)
        with mock.patch.object(bot_mod.asyncio, "sleep", mock.AsyncMock()):
            await bot_mod._send_due_reminders(now)
        self.assertEqual(self.fake_bot.recipients(), EXPECTED)


# ───────────────────────────── 08:00 / 10:10 / 20:30 ─────────────────────────────
def load_scheduler():
    """services.engagement_scheduler soxta apscheduler bilan yuklanadi (global Python'da apscheduler yo'q)."""
    class FakeScheduler:
        def __init__(self, *a, **k):
            self.jobs = []

        def add_job(self, fn, *a, **k):
            self.jobs.append(fn)

        def start(self):
            pass

    modules = {}
    for name in ("apscheduler", "apscheduler.schedulers", "apscheduler.schedulers.asyncio"):
        modules[name] = pytypes.ModuleType(name)
    modules["apscheduler.schedulers.asyncio"].AsyncIOScheduler = FakeScheduler
    with mock.patch.dict(sys.modules, modules):
        sys.modules.pop("services.engagement_scheduler", None)
        module = importlib.import_module("services.engagement_scheduler")
    return module


class EngagementJobsTest(BanFixture):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        # hamma premium bo'lsin (20:30 uchun)
        self.sql("UPDATE users SET is_premium = 1, premium_type = 'pro', premium_expires_at = ?", (wall(days=10),))
        for name, value in (("pick_morning_question", lambda uid: {"question": "Savol?", "category": "c"}),
                            ("pick_morning_greeting", lambda: "Salom"),
                            ("log_engagement_event", lambda *a, **k: True),
                            ("set_engagement_message_id", lambda *a, **k: None),
                            ("get_today_engagement", lambda *a, **k: None),
                            ("pick_premium_checkin_question", lambda: "Check-in savoli"),
                            ("prepare_premium_checkin", lambda uid, d, q, c="premium": q),
                            ("mark_premium_checkin_sent", lambda *a, **k: None)):
            patcher = mock.patch.object(engagement, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(database, "get_uz_now",
                                    return_value=dt.datetime(2026, 11, 14, 3, 0, tzinfo=UZ))   # "o'tkazib yuborilgan" ishlar yo'q
        patcher.start()
        self.addCleanup(patcher.stop)
        module = load_scheduler()
        patcher = mock.patch.object(module.asyncio, "sleep", mock.AsyncMock())
        patcher.start()
        self.addCleanup(patcher.stop)
        scheduler = module.start_scheduler(self.fake_bot, mock.AsyncMock(return_value="AI"))
        await asyncio.sleep(0)
        self.job_0800, self.job_1010, self.job_2030 = scheduler.jobs

    async def test_the_0800_message_skips_banned_users(self):
        await self.job_0800()
        self.assertEqual(self.fake_bot.recipients(), EXPECTED)

    async def test_the_1010_message_skips_banned_users(self):
        await self.job_1010()
        self.assertEqual(self.fake_bot.recipients(), EXPECTED)

    async def test_the_2030_premium_checkin_skips_banned_users(self):
        await self.job_2030()
        self.assertEqual(self.fake_bot.recipients(), EXPECTED)

    async def test_nothing_is_sent_when_everybody_is_banned(self):
        self.sql("UPDATE users SET is_banned = 1, ban_mode = 'silent', banned_until = NULL")
        for job in (self.job_0800, self.job_1010, self.job_2030):
            await job()
        self.fake_bot.send_message.assert_not_awaited()

    async def test_no_raw_is_banned_filter_is_left_in_the_scheduler(self):
        src = inspect.getsource(sys.modules.get("services.engagement_scheduler") or load_scheduler())
        self.assertNotIn("is_banned = 0", src)
        self.assertIn("get_active_user_ids", src)
        self.assertIn("get_premium_checkin_targets", src)


# ───────────────────────────── Premium tugash eslatmasi ─────────────────────────────
class PremiumExpiryReminderTest(BanFixture):
    async def test_the_one_day_before_notice_skips_banned_users(self):
        now = database.get_uz_now()
        self.sql("UPDATE users SET is_premium = 1, premium_type = 'ultra', premium_expires_at = ?",
                 ((now + dt.timedelta(hours=5)).isoformat(),))
        stats = await bot_mod.run_premium_expiry_check(now)
        self.assertEqual(self.fake_bot.recipients(), EXPECTED)
        self.assertEqual(stats["notified"], 2)

    async def test_the_check_goes_through_the_single_ban_function(self):
        src = inspect.getsource(bot_mod.run_premium_expiry_check)
        self.assertIn("user_is_banned", src)
        self.assertNotIn("is_user_banned", src)


# ───────────────────────────── referal va boshqa yuborishlar ─────────────────────────────
class ReferralNotificationTest(BanFixture):
    async def start_with_referral(self, referrer_id):
        message = mock.MagicMock()
        message.text = f"/start ref_{referrer_id}"
        message.from_user = SimpleNamespace(id=900, first_name="Yangi", last_name=None, username="new")
        message.answer = mock.AsyncMock()
        message.bot = self.fake_bot
        state = mock.MagicMock()
        state.clear = mock.AsyncMock()
        with mock.patch.object(database, "handle_referral", return_value=(True, 10, False)), \
                mock.patch.object(database, "get_referral_count", return_value=1), \
                mock.patch.object(database, "get_score", return_value=10), \
                mock.patch.object(bot_mod, "schedule_personal_menu_sync", mock.MagicMock()), \
                mock.patch.object(bot_mod, "schedule_personal_menu_reset", mock.MagicMock()):
            await bot_mod.cmd_start(message, state)

    async def test_a_banned_referrer_gets_no_notification(self):
        for referrer in (OPEN, SILENT):
            self.fake_bot.send_message.reset_mock()
            await self.start_with_referral(referrer)
            self.assertNotIn(referrer, self.fake_bot.recipients())

    async def test_a_free_referrer_is_still_notified(self):
        await self.start_with_referral(FREE)
        self.assertEqual(self.fake_bot.recipients(), [FREE])


class OtherSendPointsTest(unittest.TestCase):
    def test_every_automatic_or_admin_message_to_a_user_checks_the_ban(self):
        """Admin tasdiqlagandan keyin userga yuboriladigan xabarlar (karta cheki / reconcile), chek eslatmasi va referal
        xabari banlangan userga yuborilmaydi."""
        with open(os.path.join(PROJECT_DIR, "bot.py"), encoding="utf-8") as f:
            src = f.read()
        for anchor in ("To'lovingiz tasdiqlandi va Premium faollashtirildi", "Administrator sizga <b>1 oy Premium</b> taqdim etdi",
                       "karta to'lovingiz hali admin tomonidan tasdiqlanmagan", "Do'stingiz taklifingizni qabul qildi"):
            index = src.index(anchor)
            window = src[max(0, index - 900):index]
            self.assertIn("user_is_banned(", window, anchor)


if __name__ == "__main__":
    unittest.main()
