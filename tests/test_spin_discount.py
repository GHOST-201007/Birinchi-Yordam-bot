"""
test_spin_discount.py — P1-5: SUPER PRIZ = Premium Pro (ichki kod: plus) 30 kun uchun 50% chegirma (150 → 75 Stars).

Haqiqiy Telegram yoki bazaga murojaat qilinmaydi.
"""
import asyncio
import contextlib
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
import database  # noqa: E402
from tests.ban_shim import not_banned_patch  # noqa: E402

USER_ID = 900000501
FREE_VIEW = database.admin_premium_view(0, None, None)


class RecordingCursor:
    def __init__(self, select_row=None):
        self.select_row = select_row
        self.executed = []
        self.rowcount = 1
        self._result = None

    def execute(self, sql, params=()):
        flat = " ".join(sql.split())
        self.executed.append(flat)
        if flat.startswith("INSERT INTO payment_transactions"):
            self._result = (1,)
        elif flat.startswith("SELECT"):
            self._result = self.select_row
        else:
            self._result = None
        self.rowcount = 1

    def fetchone(self):
        return self._result

    def close(self):
        pass


class DiscountPriceTest(unittest.TestCase):
    def test_price_is_half_of_plus(self):
        with mock.patch.dict(os.environ, {"PRO_MONTHLY_STARS": "150"}):
            self.assertEqual(bot.plus_discount_price(), 75)
            self.assertEqual(bot.get_stars_tariffs()[bot.DISCOUNT_PAYLOAD], ("plus", 30, mock.ANY, 75))

    def test_validate_payment_requires_discount_amount(self):
        with mock.patch.dict(os.environ, {"PRO_MONTHLY_STARS": "150"}):
            self.assertEqual(bot.validate_payment(bot.DISCOUNT_PAYLOAD, "XTR", 75), (True, ""))
            self.assertEqual(bot.validate_payment(bot.DISCOUNT_PAYLOAD, "XTR", 1), (False, "amount"))

    def test_discount_buys_plus_tier(self):
        """Chegirma ichki plus (ko'rinadigan Pro) 30 kunga: faol plus — uzaytirish (ruxsat), pro — upgrade (ruxsat),
        ultra — pastroq tarif (taqiq)."""
        future = database.get_uz_now() + __import__("datetime").timedelta(days=10)
        for tier, allowed in (("plus", True), ("pro", True), ("ultra", False)):
            with self.subTest(tier=tier):
                view = database.admin_premium_view(1, tier, future)
                ok, reason = bot.check_premium_purchase_eligibility(view, "buy_plus_30_discount")
                self.assertEqual(ok, allowed)
                self.assertEqual(reason is None, allowed)


class DiscountInvoiceTest(unittest.TestCase):
    def make_callback(self):
        cb = mock.MagicMock()
        cb.data = "buy_plus_30_discount"
        cb.from_user = SimpleNamespace(id=USER_ID)
        cb.answer = mock.AsyncMock()
        cb.message.answer_invoice = mock.AsyncMock()
        return cb

    def run_invoice(self, has_discount):
        cb = self.make_callback()
        with mock.patch.dict(os.environ, {"PRO_MONTHLY_STARS": "150"}), \
             mock.patch.object(bot.database, "get_premium_view", return_value=FREE_VIEW), \
             mock.patch.object(bot.database, "has_discount", return_value=has_discount):
            asyncio.run(bot.process_pay_stars_tariff(cb))
        return cb

    def test_invoice_with_discount(self):
        cb = self.run_invoice(True)
        kwargs = cb.message.answer_invoice.await_args.kwargs
        self.assertEqual(kwargs["payload"], bot.DISCOUNT_PAYLOAD)
        self.assertEqual(kwargs["prices"][0].amount, 75)

    def test_no_invoice_without_discount(self):
        cb = self.run_invoice(False)
        cb.message.answer_invoice.assert_not_awaited()
        cb.answer.assert_awaited()


class DiscountPreCheckoutTest(unittest.TestCase):
    def run_pre_checkout(self, has_discount):
        q = mock.MagicMock()
        q.from_user = SimpleNamespace(id=USER_ID)
        q.invoice_payload = bot.DISCOUNT_PAYLOAD
        q.currency = "XTR"
        q.total_amount = 75
        q.answer = mock.AsyncMock()
        with mock.patch.dict(os.environ, {"PRO_MONTHLY_STARS": "150"}), \
             mock.patch.object(bot.database, "is_user_banned", return_value=(False, None)), \
             not_banned_patch(), \
             mock.patch.object(bot.database, "get_premium_view", return_value=FREE_VIEW), \
             mock.patch.object(bot.database, "has_discount", return_value=has_discount):
            asyncio.run(bot.process_pre_checkout(q))
        return q.answer.await_args.kwargs

    def test_accepted_with_discount(self):
        self.assertTrue(self.run_pre_checkout(True)["ok"])

    def test_rejected_when_discount_used(self):
        self.assertFalse(self.run_pre_checkout(False)["ok"])


class DiscountDatabaseTest(unittest.TestCase):
    def test_paid_premium_consumes_discount_in_same_transaction(self):
        cursor = RecordingCursor(select_row=(None, "free"))
        conn = mock.MagicMock()
        conn.cursor.return_value = cursor
        with mock.patch.object(database, "get_connection", return_value=conn):
            granted, _ = database.process_paid_premium(
                "ch_disc", USER_ID, bot.DISCOUNT_PAYLOAD, 75, "plus", 30, True)
        self.assertTrue(granted)
        self.assertTrue(any("has_discount = 0" in q for q in cursor.executed))
        conn.commit.assert_called_once()

    def test_paid_premium_without_flag_keeps_discount(self):
        cursor = RecordingCursor(select_row=(None, "free"))
        conn = mock.MagicMock()
        conn.cursor.return_value = cursor
        with mock.patch.object(database, "get_connection", return_value=conn):
            database.process_paid_premium("ch_norm", USER_ID, "PLUS_30_DAYS", 150, "plus", 30)
        self.assertFalse(any("has_discount" in q for q in cursor.executed))

    def test_super_prize_message_promises_75_stars(self):
        cursor = RecordingCursor(select_row=(None, 0))  # last_spin_date=None, pending_spin_prize=0 (SUPER)
        conn = mock.MagicMock()

        @contextlib.contextmanager
        def fake_managed():
            yield conn, cursor

        with mock.patch.dict(os.environ, {"PRO_MONTHLY_STARS": "150"}), \
             mock.patch.object(database, "_managed_cursor", fake_managed):
            ok, msg = database.check_and_grant_spin_bonus(USER_ID, 0)
        self.assertTrue(ok)
        self.assertIn("75 Stars", msg)
        self.assertIn("Premium Pro", msg)                      # ichki plus = ko'rinadigan Pro
        self.assertNotIn("Premium Plus", msg)
        self.assertNotIn("20 Stars", msg)


if __name__ == "__main__":
    unittest.main()
