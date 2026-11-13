"""
test_super_discount.py — SUPER PRIZ: 24 soatlik −50% Pro taklifi (ichki plus, 30 kun, 150⭐ -> 75⭐).

Qamrov:
  DB       — SUPER -> discount_expires_at = +24 soat, qayta yutish muddatni suradi, 24 soatdan keyin faol emas,
             migratsiya eski chegirmaga 24 soat beradi va ikkinchi marta o'zgartirmaydi, narx formulasi yagona.
  To'lov   — faol chegirmada invoice 75, muddat o'tgach 150; muddati o'tgan chegirmali invoice pre_checkout da rad;
             chegirma FAQAT muvaffaqiyatli to'lovdan keyin sarflanadi; Ultra / muddatsiz Premiumda taklif yo'q.
  Bot      — yutgan xabarda invoice tugmasi va muddat; 24 soat ichida Pro sotiladigan HAMMA joyda faqat chegirmali tugma,
             keyin oddiy tugma; qolgan vaqt formati.
  API      — /api/state va spin claim da `discount` maydoni; muddat o'tgach active: false.

DB mantig'i HAQIQIY SQL bilan (tests/sqlite_db.py); Telegram, Gemini va PostgreSQL ishlatilmaydi.
"""
import asyncio
import datetime as dt
import os
import sqlite3
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("BOT_TOKEN", "123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567890")
os.environ.setdefault("GEMINI_API_KEY", "test_gemini_key")

import bot  # noqa: E402
import database  # noqa: E402
from tests.discount_helpers import discount_info  # noqa: E402
from tests.sqlite_db import SqliteDB  # noqa: E402
from tests.test_miniapp_api import ApiTestBase, spin_result  # noqa: E402

UID = 900001001
UZ = dt.timezone(dt.timedelta(hours=5))
FIXED = dt.datetime(2026, 11, 14, 16, 5, tzinfo=UZ)          # qat'iy "hozir" (now= parametri bilan)
H24 = dt.timedelta(hours=24)
ENV = {"PRO_MONTHLY_STARS": "150", "PRO_TRIAL_STARS": "50", "ULTRA_MONTHLY_STARS": "300"}
FREE_VIEW = database.admin_premium_view(0, None, None)


def active_view(tier, days=10):
    return database.admin_premium_view(1, tier, database.get_uz_now() + dt.timedelta(days=days))


def unlimited_view(tier="ultra"):
    return database.admin_premium_view(1, tier, None)


def buttons(markup):
    return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row if b.callback_data]


# ═══════════════════════════════ DB ═══════════════════════════════
class DbBase(unittest.TestCase):
    def setUp(self):
        self.db = SqliteDB()
        self.addCleanup(self.db.close)
        con = sqlite3.connect(self.db.path)
        con.execute("""CREATE TABLE payment_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, charge_id TEXT UNIQUE, user_id INTEGER, product_id TEXT,
            stars_amount INTEGER, premium_type TEXT, duration_days INTEGER)""")
        con.commit()
        con.close()
        patcher = self.db.patched()
        patcher.start()
        self.addCleanup(patcher.stop)

    def row(self):
        return self.db.row(UID)

    def set_discount(self, delta, uid=UID):
        """Foydalanuvchiga hozirdan delta keyin tugaydigan chegirma beradi (yo'q bo'lsa yaratadi, bor bo'lsa yangilaydi)."""
        until = (database.get_uz_now() + delta).isoformat()
        if self.db.row(uid) is None:
            self.db.add_user(uid, has_discount=1, discount_expires_at=until)
            return
        con = sqlite3.connect(self.db.path)
        con.execute("UPDATE users SET has_discount = 1, discount_expires_at = ? WHERE user_id = ?", (until, uid))
        con.commit()
        con.close()


class WinningTest(DbBase):
    def win(self, **cols):
        self.db.add_user(UID, pending_spin_prize=0, medicine_score=10, **cols)
        with mock.patch.dict(os.environ, ENV):
            return database.claim_spin_prize(UID)

    def test_super_gives_24_hour_discount(self):
        before = database.get_uz_now()
        result = self.win()
        after = database.get_uz_now()
        self.assertTrue(result["ok"])
        self.assertEqual(result["prize_type"], "super")
        row = self.row()
        self.assertEqual(row["has_discount"], 1)
        expires = database._to_uz_datetime(row["discount_expires_at"])
        self.assertTrue(before + H24 <= expires <= after + H24)

    def test_result_carries_the_new_discount_for_the_invoice_button_and_the_app(self):
        result = self.win()
        info = result["discount"]
        self.assertTrue(info["active"])
        self.assertEqual((info["price"], info["old_price"]), (75, 150))
        self.assertAlmostEqual(info["seconds_left"], 24 * 3600, delta=5)
        self.assertEqual(info["expires_at"], database._to_uz_datetime(self.row()["discount_expires_at"]))

    def test_message_states_the_price_and_the_deadline(self):
        result = self.win()
        expires = database._to_uz_datetime(self.row()["discount_expires_at"])
        self.assertIn("75 Stars", result["message"])
        self.assertIn("24 soat amal qiladi", result["message"])
        self.assertIn(f"{expires:%d.%m.%Y %H:%M}", result["message"])

    def test_other_prizes_do_not_touch_the_discount(self):
        for code in (1, 2, 3, 5, -1, -2):
            with self.subTest(code=code):
                self.setUp()
                self.db.add_user(UID, pending_spin_prize=code)
                result = database.claim_spin_prize(UID)
                self.assertTrue(result["ok"])
                self.assertNotIn("discount", result)
                self.assertEqual((self.row()["has_discount"], self.row()["discount_expires_at"]), (0, None))

    def test_winning_again_extends_the_deadline_to_a_fresh_24_hours(self):
        soon = database.get_uz_now() + dt.timedelta(hours=2)
        result = self.win(has_discount=1, discount_expires_at=soon.isoformat())
        expires = database._to_uz_datetime(self.row()["discount_expires_at"])
        self.assertGreater(expires, soon + dt.timedelta(hours=21))
        self.assertAlmostEqual(result["discount"]["seconds_left"], 24 * 3600, delta=5)

    def test_a_second_claim_does_not_extend_again(self):
        self.win()
        first = self.row()["discount_expires_at"]
        again = database.claim_spin_prize(UID)                       # pending_spin_prize allaqachon NULL
        self.assertFalse(again["ok"])
        self.assertEqual(self.row()["discount_expires_at"], first)


class InfoTest(DbBase):
    def info(self, now):
        return database.get_discount_info(UID, now=now)

    def test_active_before_the_deadline_with_seconds_left(self):
        self.db.add_user(UID, has_discount=1, discount_expires_at=(FIXED + H24).isoformat())
        info = self.info(FIXED)
        self.assertTrue(info["active"])
        self.assertEqual(info["seconds_left"], 24 * 3600)
        self.assertEqual((info["price"], info["old_price"]), (75, 150))
        self.assertEqual(self.info(FIXED + dt.timedelta(hours=19))["seconds_left"], 5 * 3600)

    def test_inactive_after_24_hours_and_exactly_at_the_deadline(self):
        until = FIXED + H24
        self.db.add_user(UID, has_discount=1, discount_expires_at=until.isoformat())
        for now in (until, until + dt.timedelta(seconds=1), until + dt.timedelta(days=3)):
            with self.subTest(now=now):
                info = self.info(now)
                self.assertFalse(info["active"])
                self.assertIsNone(info["expires_at"])
                self.assertEqual(info["seconds_left"], 0)

    def test_expired_discount_is_not_written_back_on_read(self):
        until = FIXED + H24
        self.db.add_user(UID, has_discount=1, discount_expires_at=until.isoformat())
        self.info(until + dt.timedelta(hours=1))
        self.assertEqual(self.row()["has_discount"], 1)
        self.assertEqual(self.row()["discount_expires_at"], until.isoformat())

    def test_flag_off_or_missing_deadline_or_missing_user_means_inactive(self):
        self.db.add_user(UID, has_discount=0, discount_expires_at=(FIXED + H24).isoformat())
        self.assertFalse(self.info(FIXED)["active"])
        self.db.add_user(UID + 1, has_discount=1, discount_expires_at=None)
        self.assertFalse(database.get_discount_info(UID + 1, now=FIXED)["active"])
        self.assertFalse(database.get_discount_info(UID + 2, now=FIXED)["active"])

    def test_naive_timestamp_from_postgres_is_read_as_tashkent_time(self):
        self.db.add_user(UID, has_discount=1, discount_expires_at="2026-11-15 16:05:00")
        self.assertTrue(self.info(FIXED)["active"])
        self.assertFalse(self.info(FIXED + H24)["active"])

    def test_has_discount_follows_the_expiry(self):
        self.db.add_user(UID, has_discount=1, discount_expires_at=(database.get_uz_now() + dt.timedelta(hours=1)).isoformat())
        self.assertTrue(database.has_discount(UID))
        self.db.add_user(UID + 1, has_discount=1, discount_expires_at=(database.get_uz_now() - dt.timedelta(seconds=1)).isoformat())
        self.assertFalse(database.has_discount(UID + 1))

    def test_has_discount_is_false_when_the_database_fails(self):
        with mock.patch.object(database, "get_discount_info", side_effect=RuntimeError("db")):
            self.assertFalse(database.has_discount(UID))


class MigrationTest(DbBase):
    def migrate(self, now=FIXED):
        conn = database.get_connection()
        cur = conn.cursor()
        count = database.migrate_discount_expiry(cur, now=now)
        conn.commit()
        conn.close()
        return count

    def test_old_unlimited_discount_gets_24_hours_from_the_deploy(self):
        self.db.add_user(UID, has_discount=1)
        self.assertEqual(self.migrate(), 1)
        self.assertEqual(database._to_uz_datetime(self.row()["discount_expires_at"]), FIXED + H24)

    def test_second_run_changes_nothing(self):
        self.db.add_user(UID, has_discount=1)
        self.migrate()
        first = self.row()["discount_expires_at"]
        self.assertEqual(self.migrate(now=FIXED + dt.timedelta(hours=10)), 0)
        self.assertEqual(self.row()["discount_expires_at"], first)

    def test_only_users_with_a_flag_and_no_deadline_are_touched(self):
        later = (FIXED + dt.timedelta(hours=3)).isoformat()
        self.db.add_user(UID, has_discount=0)                                      # chegirma yo'q
        self.db.add_user(UID + 1, has_discount=1, discount_expires_at=later)       # muddati allaqachon bor
        self.db.add_user(UID + 2, has_discount=1)                                  # eski, muddatsiz
        self.assertEqual(self.migrate(), 1)
        self.assertIsNone(self.db.row(UID)["discount_expires_at"])
        self.assertEqual(self.db.row(UID + 1)["discount_expires_at"], later)
        self.assertIsNotNone(self.db.row(UID + 2)["discount_expires_at"])

    def test_init_db_adds_the_column_in_existing_style_and_runs_the_migration(self):
        executed = []
        cursor = mock.MagicMock()
        cursor.execute.side_effect = lambda sql, params=(): executed.append(" ".join(sql.split()))
        cm = mock.MagicMock()
        cm.__enter__.return_value = (mock.MagicMock(), cursor)
        with mock.patch.object(database, "_managed_cursor", return_value=cm):
            database.init_db()
        self.assertIn("ALTER TABLE users ADD COLUMN IF NOT EXISTS discount_expires_at TIMESTAMP", executed)
        create_users = next(q for q in executed if q.startswith("CREATE TABLE IF NOT EXISTS users"))
        self.assertIn("discount_expires_at TIMESTAMP", create_users)
        self.assertIn("has_discount INTEGER DEFAULT 0", create_users)                   # eski ustun o'zgarmagan
        update = [q for q in executed if q.startswith("UPDATE users SET discount_expires_at")]
        self.assertEqual(len(update), 1)
        self.assertIn("has_discount = 1 AND discount_expires_at IS NULL", update[0])    # idempotent shart
        self.assertLess(executed.index("ALTER TABLE users ADD COLUMN IF NOT EXISTS discount_expires_at TIMESTAMP"),
                        executed.index(update[0]))


class PriceFormulaTest(unittest.TestCase):
    def test_discount_is_half_rounded_up_and_never_zero(self):
        for price, expected in ((150, 75), (151, 76), (200, 100), (1, 1), (2, 1)):
            with self.subTest(price=price):
                self.assertEqual(database.plus_discount_price(price), expected)

    def test_price_follows_the_env_and_bot_uses_the_same_formula(self):
        with mock.patch.dict(os.environ, {"PRO_MONTHLY_STARS": "200"}):
            self.assertEqual(database.plus_price(), 200)
            self.assertEqual(database.plus_discount_price(), 100)
            self.assertEqual(bot.plus_discount_price(), 100)
            self.assertEqual(bot.discount_plus_offer()[3], 100)
            self.assertEqual(discount_info()["price"], 100)

    def test_bot_has_no_second_formula(self):
        self.assertIs(bot.plus_discount_price, database.plus_discount_price)


# ═══════════════════════════════ To'lov ═══════════════════════════════
class PaymentTest(DbBase):
    def offer(self, action="buy_plus_30"):
        with mock.patch.dict(os.environ, ENV):
            return asyncio.run(bot.build_premium_offer(UID, action))

    def give(self, delta, uid=UID):
        self.set_discount(delta, uid)

    def test_invoice_is_75_while_active_and_150_after_expiry(self):
        self.give(dt.timedelta(hours=1))
        _title, _desc, payload, stars = self.offer()
        self.assertEqual((payload, stars), (bot.DISCOUNT_PAYLOAD, 75))
        self.give(-dt.timedelta(seconds=1), uid=UID + 1)
        with mock.patch.dict(os.environ, ENV):
            _title, _desc, payload, stars = asyncio.run(bot.build_premium_offer(UID + 1, "buy_plus_30"))
        self.assertEqual((payload, stars), ("PLUS_30_DAYS", 150))

    def test_discount_button_after_expiry_is_refused(self):
        self.give(-dt.timedelta(minutes=1))
        with self.assertRaises(bot.OfferUnavailable):
            self.offer("buy_plus_30_discount")

    def test_other_tariffs_are_never_discounted(self):
        self.give(dt.timedelta(hours=1))
        self.assertEqual(self.offer("buy_pro_7")[3], 50)
        self.assertEqual(self.offer("buy_ultra_30")[3], 300)

    def pre_checkout(self, payload=None, amount=75, view=FREE_VIEW):
        query = mock.MagicMock()
        query.from_user = SimpleNamespace(id=UID)
        query.invoice_payload = payload or bot.DISCOUNT_PAYLOAD
        query.currency = "XTR"
        query.total_amount = amount
        query.answer = mock.AsyncMock()
        with mock.patch.dict(os.environ, ENV), \
             mock.patch.object(bot.database, "is_user_banned", return_value=(False, None)), \
             mock.patch.object(bot.database, "get_premium_view", return_value=view):
            asyncio.run(bot.process_pre_checkout(query))
        return query.answer.await_args.kwargs

    def test_pre_checkout_accepts_the_discounted_invoice_while_active(self):
        self.give(dt.timedelta(hours=1))
        self.assertEqual(self.pre_checkout(), {"ok": True})

    def test_pre_checkout_rejects_an_expired_discount_invoice(self):
        self.give(-dt.timedelta(seconds=1))
        answer = self.pre_checkout()
        self.assertFalse(answer["ok"])
        self.assertEqual(answer["error_message"], "⏳ Chegirma muddati tugagan. Pro tarifini oddiy narxda olishingiz mumkin.")
        self.assertEqual(answer["error_message"], bot.DISCOUNT_EXPIRED_TEXT)

    def test_pre_checkout_rejects_75_for_the_normal_payload(self):
        self.give(dt.timedelta(hours=1))
        self.assertFalse(self.pre_checkout(payload="PLUS_30_DAYS", amount=75)["ok"])        # 75 faqat chegirma payload'i uchun
        self.assertTrue(self.pre_checkout(payload="PLUS_30_DAYS", amount=150)["ok"])

    def test_pre_checkout_rejects_an_already_used_discount(self):
        self.give(dt.timedelta(hours=1))
        database.consume_discount(UID)
        answer = self.pre_checkout()
        self.assertFalse(answer["ok"])
        self.assertEqual(answer["error_message"], bot.DISCOUNT_EXPIRED_TEXT)

    def test_pre_checkout_rejects_other_amounts_for_the_discount_payload(self):
        self.give(dt.timedelta(hours=1))
        for amount in (74, 100, 150, 76):
            with self.subTest(amount=amount):
                self.assertFalse(self.pre_checkout(amount=amount)["ok"])

    def test_alert_for_an_expired_discount_button(self):
        self.give(-dt.timedelta(minutes=5))
        callback = mock.MagicMock()
        callback.data = "buy_plus_30_discount"
        callback.from_user = SimpleNamespace(id=UID)
        callback.answer = mock.AsyncMock()
        callback.message.answer_invoice = mock.AsyncMock()
        with mock.patch.dict(os.environ, ENV), mock.patch.object(bot.database, "get_premium_view", return_value=FREE_VIEW):
            asyncio.run(bot.process_pay_stars_tariff(callback))
        callback.message.answer_invoice.assert_not_awaited()
        self.assertEqual(callback.answer.await_args.args[0], bot.DISCOUNT_EXPIRED_TEXT)

    # ---- chegirma FAQAT muvaffaqiyatli to'lovdan keyin sarflanadi ----
    def test_creating_the_invoice_and_pre_checkout_do_not_consume_the_discount(self):
        self.give(dt.timedelta(hours=1))
        self.offer()
        self.pre_checkout()
        self.assertEqual(self.row()["has_discount"], 1)
        self.assertIsNotNone(self.row()["discount_expires_at"])

    def test_successful_payment_consumes_the_discount_and_grants_premium(self):
        self.give(dt.timedelta(hours=1))
        granted, until = database.process_paid_premium("ch_1", UID, bot.DISCOUNT_PAYLOAD, 75, "plus", 30, True)
        self.assertTrue(granted)
        row = self.row()
        self.assertEqual((row["has_discount"], row["discount_expires_at"]), (0, None))
        self.assertEqual((row["is_premium"], row["premium_type"]), (1, "plus"))
        self.assertFalse(database.has_discount(UID))
        self.assertFalse(database.get_discount_info(UID)["active"])

    def test_duplicate_charge_does_not_consume_a_newly_won_discount(self):
        self.give(dt.timedelta(hours=1))
        database.process_paid_premium("ch_dup", UID, bot.DISCOUNT_PAYLOAD, 75, "plus", 30, True)
        self.give(dt.timedelta(hours=24))                                  # keyin yangi SUPER yutildi
        granted, _ = database.process_paid_premium("ch_dup", UID, bot.DISCOUNT_PAYLOAD, 75, "plus", 30, True)
        self.assertFalse(granted)
        self.assertEqual(self.row()["has_discount"], 1)

    def test_normal_payment_keeps_the_discount(self):
        self.give(dt.timedelta(hours=1))
        database.process_paid_premium("ch_norm", UID, "PRO_7_DAYS", 50, "pro", 7)
        self.assertEqual(self.row()["has_discount"], 1)

    def test_consume_discount_clears_the_deadline_too(self):
        self.give(dt.timedelta(hours=1))
        database.consume_discount(UID)
        self.assertEqual((self.row()["has_discount"], self.row()["discount_expires_at"]), (0, None))

    # ---- Pro sotib olish mumkin bo'lmasa taklif yo'q ----
    def test_no_offer_for_ultra_or_unlimited_premium(self):
        info = discount_info()

        async def offer_for(view):
            with mock.patch.object(bot.database, "has_discount", return_value=True), \
                 mock.patch.object(bot.database, "get_discount_info", return_value=info):
                return await bot.pro_discount_for(UID, view)

        self.assertIsNone(asyncio.run(offer_for(active_view("ultra"))))
        self.assertIsNone(asyncio.run(offer_for(unlimited_view("ultra"))))
        self.assertIsNone(asyncio.run(offer_for(unlimited_view("plus"))))
        for view in (FREE_VIEW, active_view("pro"), active_view("plus")):
            with self.subTest(tier=view["tier"]):
                self.assertEqual(asyncio.run(offer_for(view)), info)

    def test_no_offer_when_the_discount_is_not_active(self):
        async def offer():
            with mock.patch.object(bot.database, "has_discount", return_value=False):
                return await bot.pro_discount_for(UID, FREE_VIEW)

        self.assertIsNone(asyncio.run(offer()))

    def test_no_offer_when_the_database_fails(self):
        async def offer():
            with mock.patch.object(bot.database, "has_discount", side_effect=RuntimeError("db")):
                return await bot.pro_discount_for(UID, FREE_VIEW)

        self.assertIsNone(asyncio.run(offer()))


# ═══════════════════════════════ Bot matnlari va tugmalar ═══════════════════════════════
class LeftFormatTest(unittest.TestCase):
    def left(self, **delta):
        return bot.format_discount_left(FIXED + dt.timedelta(**delta), now=FIXED)

    def test_formats(self):
        self.assertEqual(self.left(hours=24), "24 soat")
        self.assertEqual(self.left(hours=23, minutes=40), "23 soat 40 daqiqa")
        self.assertEqual(self.left(hours=5, minutes=12), "5 soat 12 daqiqa")
        self.assertEqual(self.left(hours=5), "5 soat")
        self.assertEqual(self.left(hours=1), "1 soat")
        self.assertEqual(self.left(minutes=40), "40 daqiqa")
        self.assertEqual(self.left(minutes=1), "1 daqiqa")

    def test_rounds_minutes_up_and_never_goes_negative(self):
        self.assertEqual(self.left(seconds=30), "1 daqiqa")
        self.assertEqual(self.left(hours=23, minutes=59, seconds=30), "24 soat")
        self.assertEqual(self.left(seconds=-5), "0 daqiqa")
        self.assertEqual(self.left(hours=-3), "0 daqiqa")


class WinMessageTest(unittest.TestCase):
    """/start spin_* (Mini App zaxira yo'li va botdagi tasdiq): yutgan zahoti matn + to'g'ridan-to'g'ri invoice tugmasi."""

    def start(self, view, result):
        message = mock.MagicMock()
        message.text = "/start spin_super"
        message.from_user = SimpleNamespace(id=UID, first_name="Ali", last_name=None, username="ali")
        message.answer = mock.AsyncMock()
        state = mock.MagicMock()
        state.clear = mock.AsyncMock()
        with mock.patch.dict(os.environ, ENV), \
             mock.patch.object(bot.database, "register_user"), \
             mock.patch.object(bot.database, "get_premium_view", return_value=view), \
             mock.patch.object(bot.database, "claim_spin_prize", return_value=result):
            asyncio.run(bot.cmd_start(message, state))
        args, kwargs = message.answer.await_args
        return args[0], kwargs["reply_markup"]

    def result(self, **extra):
        base = {"ok": True, "message": "OLD-SUPER-TEXT", "code": 0, "prize_type": "super", "points": 0, "tip": None,
                "discount": discount_info(hours=24)}
        base.update(extra)
        return base

    def test_text_has_prices_deadline_and_the_invoice_button(self):
        text, markup = self.start(FREE_VIEW, self.result())
        until = database.get_uz_now() + H24
        self.assertIn("🏆 <b>SUPER PRIZ!</b>", text)
        self.assertIn("💎 Pro (30 kun) — <b>50% chegirma</b>", text)
        self.assertIn("<s>150⭐</s> → <b>75⭐</b>", text)
        self.assertIn("⏳ Taklif 24 soat amal qiladi:", text)
        self.assertIn(f"{until:%d.%m.%Y}", text)
        self.assertEqual(buttons(markup), [("💎 Pro — 75⭐ (−50%)", "buy_plus_30_discount")])

    def test_active_pro_extends_with_the_discount(self):
        _text, markup = self.start(active_view("plus"), self.result())
        self.assertEqual(buttons(markup), [("🔄 Pro — yana 30 kun — 75⭐ (−50%)", "buy_plus_30_discount")])

    def test_ultra_and_unlimited_keep_the_existing_text_and_no_discount_button(self):
        for view in (active_view("ultra"), unlimited_view("plus")):
            with self.subTest(tier=view["tier"], unlimited=view["unlimited"]):
                text, markup = self.start(view, self.result())
                self.assertEqual(text, "OLD-SUPER-TEXT")
                self.assertEqual(buttons(markup), [("💎 Premium xarid qilish", "buy_premium")])

    def test_user_text_is_not_needed_to_be_escaped_but_html_is_valid(self):
        text, _markup = self.start(FREE_VIEW, self.result())
        self.assertEqual(text.count("<b>"), text.count("</b>"))
        self.assertEqual(text.count("<s>"), text.count("</s>"))


class EverywhereTest(unittest.IsolatedAsyncioTestCase):
    """24 soat ichida Pro sotiladigan HAR BIR joyda faqat chegirmali tugma + eski narx + qolgan vaqt; keyin oddiy tugma."""

    def patches(self, active, view=FREE_VIEW):
        info = discount_info(active, hours=5, minutes=12)
        return (mock.patch.dict(os.environ, {**ENV, "MINI_APP_URL": "https://app.example/index.html"}),
                mock.patch.object(database, "has_discount", return_value=active),
                mock.patch.object(database, "get_discount_info", return_value=info),
                mock.patch.object(database, "get_score", return_value=7),
                mock.patch.object(database, "get_premium_view", return_value=view),
                mock.patch.object(database, "get_ai_quota_detail", return_value=(10, 30, 0)),
                mock.patch.object(bot, "get_web_app_url", mock.AsyncMock(return_value="https://x/app")))

    def target(self):
        target = mock.MagicMock()
        target.from_user = SimpleNamespace(id=UID)
        target.answer = mock.AsyncMock()
        return target

    async def run_with(self, active, coro_factory, view=FREE_VIEW):
        stack = self.patches(active, view)
        for p in stack:
            p.start()
            self.addCleanup(p.stop)
        return await coro_factory()

    def sent(self, target):
        args, kwargs = target.answer.await_args
        return args[0], buttons(kwargs["reply_markup"])

    async def page(self, active, view=FREE_VIEW):
        target = self.target()
        await self.run_with(active, lambda: bot._show_premium_sales(target, view), view)
        return self.sent(target)

    async def test_sales_page_free_user(self):
        text, btns = await self.page(True)
        callbacks = [c for _t, c in btns]
        self.assertIn(("💎 Pro — 75⭐ (−50%)", "buy_plus_30_discount"), btns)
        self.assertNotIn("buy_plus_30", callbacks)                              # oddiy 150⭐ Pro tugmasi yo'q
        self.assertIn("<s>150⭐</s> <b>75⭐</b>", text)
        self.assertIn("5 soat 12 daqiqa qoldi", text)
        self.assertNotIn("150 ⭐ → 30 kun", text)

    async def test_sales_page_after_expiry_is_normal(self):
        text, btns = await self.page(False)
        callbacks = [c for _t, c in btns]
        self.assertIn("buy_plus_30", callbacks)
        self.assertNotIn("buy_plus_30_discount", callbacks)
        self.assertNotIn("<s>150⭐</s>", text)
        self.assertNotIn("qoldi", text)
        self.assertIn(("💎 150 Stars → 30 kun Premium Pro", "buy_plus_30"), btns)

    async def test_sales_page_other_tiers_keep_their_normal_buttons(self):
        _text, btns = await self.page(True)
        self.assertIn(("⭐ 50 Stars → 7 kun Premium Plus", "buy_pro_7"), btns)
        self.assertIn(("👑 300 Stars → 30 kun Premium Ultra", "buy_ultra_30"), btns)

    async def test_my_premium_page(self):
        for active in (True, False):
            with self.subTest(active=active):
                view = active_view("plus", days=5)
                target = self.target()
                with mock.patch.object(database, "get_ai_quota_detail", return_value=(10, 30, 0)), \
                     mock.patch.object(database, "has_discount", return_value=active), \
                     mock.patch.object(database, "get_discount_info", return_value=discount_info(active, hours=5, minutes=12)), \
                     mock.patch.dict(os.environ, {**ENV, "MINI_APP_URL": "https://app.example/index.html"}):
                    await bot._show_my_premium_page(target, UID, view)
                text, btns = self.sent(target)
                callbacks = [c for _t, c in btns]
                if active:
                    self.assertEqual(btns[0], ("🔄 Pro — yana 30 kun — 75⭐ (−50%)", "buy_plus_30_discount"))
                    self.assertIn("5 soat 12 daqiqa qoldi", text)
                    self.assertIn("<s>150⭐</s>", text)
                else:
                    self.assertNotIn("buy_plus_30_discount", callbacks)
                    self.assertNotIn("qoldi", text.split("AI limit")[-1])

    async def test_ai_limit_upsell(self):
        for active in (True, False):
            with self.subTest(active=active):
                event = mock.MagicMock(spec=bot.types.Message)
                event.from_user = SimpleNamespace(id=UID)
                event.answer = mock.AsyncMock()
                with mock.patch.object(database, "get_premium_info", return_value=(0, None, "free")), \
                     mock.patch.object(database, "has_discount", return_value=active), \
                     mock.patch.object(database, "get_discount_info", return_value=discount_info(active, hours=5, minutes=12)):
                    await bot.premium_upsell(event)
                args, kwargs = event.answer.await_args
                text, btns = args[0], buttons(kwargs["reply_markup"])
                if active:
                    self.assertEqual(btns[0], ("💎 Pro — 75⭐ (−50%)", "buy_plus_30_discount"))
                    self.assertIn("<s>150⭐</s> <b>75⭐</b>", text)
                    self.assertIn("5 soat 12 daqiqa qoldi", text)
                else:
                    self.assertEqual(btns, [("💎 Premium", "buy_premium")])
                    self.assertNotIn("<s>150⭐</s>", text)

    async def test_ai_limit_upsell_for_ultra_has_no_discount(self):
        event = mock.MagicMock(spec=bot.types.Message)
        event.from_user = SimpleNamespace(id=UID)
        event.answer = mock.AsyncMock()
        until = database.get_uz_now() + dt.timedelta(days=5)
        with mock.patch.object(database, "get_premium_info", return_value=(1, until, "ultra")), \
             mock.patch.object(database, "has_discount", return_value=True), \
             mock.patch.object(database, "get_discount_info", return_value=discount_info(True)):
            await bot.premium_upsell(event)
        args, kwargs = event.answer.await_args
        self.assertNotIn("<s>150⭐</s>", args[0])
        self.assertIsNone(kwargs["reply_markup"])


# ═══════════════════════════════ API ═══════════════════════════════
class ApiDiscountTest(ApiTestBase):
    def set_discount(self, hours=5, minutes=12):
        self.m["discount"].side_effect = lambda uid: discount_info(True, hours=hours, minutes=minutes)

    async def test_state_carries_the_active_discount(self):
        self.set_discount()
        _resp, data = await self.post("/api/state")
        d = data["discount"]
        self.assertTrue(d["active"])
        self.assertEqual((d["price"], d["old_price"]), (75, 150))
        self.assertAlmostEqual(d["seconds_left"], 5 * 3600 + 12 * 60, delta=5)
        self.assertEqual(sorted(d), ["active", "expires_at", "old_price", "price", "seconds_left"])
        expires = dt.datetime.fromisoformat(d["expires_at"])
        self.assertEqual(expires.utcoffset(), dt.timedelta(hours=5))                  # Toshkent vaqti
        self.assertAlmostEqual((expires - database.get_uz_now()).total_seconds(), d["seconds_left"], delta=5)

    async def test_state_after_expiry_is_inactive(self):
        _resp, data = await self.post("/api/state")
        self.assertEqual(data["discount"], {"active": False, "price": 75, "old_price": 150,
                                            "expires_at": None, "seconds_left": 0})

    async def test_expired_discount_from_the_database_is_inactive_in_the_api(self):
        self.m["discount"].side_effect = lambda uid: database._discount_view(
            1, database.get_uz_now() - dt.timedelta(seconds=1))
        _resp, data = await self.post("/api/state")
        self.assertFalse(data["discount"]["active"])
        self.assertEqual(data["discount"]["seconds_left"], 0)
        self.assertIsNone(data["discount"]["expires_at"])

    async def test_state_survives_a_discount_read_error(self):
        self.m["discount"].side_effect = RuntimeError("db down")
        resp, data = await self.post("/api/state")
        self.assertEqual(resp.status, 200)
        self.assertFalse(data["discount"]["active"])

    async def test_premium_quota_fields_include_the_discount(self):
        self.set_discount()
        fields = await bot._premium_quota_fields(424242)
        self.assertTrue(fields["discount"]["active"])

    async def test_redeem_response_also_carries_the_discount(self):
        self.set_discount()
        with mock.patch.object(bot, "redeem_points_for_premium", mock.AsyncMock(return_value={
                "ok": False, "reason": "not_enough", "message": "yetarli emas", "score": 3, "view": None})):
            _resp, data = await self.post("/api/points/redeem")
        self.assertTrue(data["discount"]["active"])

    async def test_super_claim_returns_the_new_discount_without_an_extra_request(self):
        info = discount_info(True, hours=24)
        self.m["spin"].return_value = spin_result(message="SUPER", code=0, prize_type="super", points=0)
        self.m["spin"].return_value["discount"] = info
        _resp, data = await self.post("/api/spin/claim")
        self.assertTrue(data["is_super"])
        self.assertTrue(data["discount"]["active"])
        self.assertAlmostEqual(data["discount"]["seconds_left"], 24 * 3600, delta=5)
        self.assertEqual(data["discount"]["expires_at"], info["expires_at"].isoformat())
        self.m["discount"].assert_not_called()                                         # qo'shimcha DB so'rovi yo'q

    async def test_non_super_claim_has_no_discount_field(self):
        _resp, data = await self.post("/api/spin/claim")
        self.assertNotIn("discount", data)
        self.m["spin"].return_value = spin_result(ok=False, message="allaqachon olingan")
        _resp, data = await self.post("/api/spin/claim")
        self.assertNotIn("discount", data)


if __name__ == "__main__":
    unittest.main()
