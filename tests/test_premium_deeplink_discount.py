"""
test_premium_deeplink_discount.py — 6-qadam: ?start=buy_plus_30 deep link chegirmani hisobga oladi.

SUPER PRIZ yutgan foydalanuvchi mini appdagi "Premium olish" tugmasi (?start=buy_plus_30) orqali kelganda
to'liq narx emas, chegirmali (50%) narx so'ralishi kerak. Haqiqiy Telegram yoki bazaga murojaat qilinmaydi.
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

USER_ID = 900000601
FREE_VIEW = bot.database.admin_premium_view(0, None, None)      # /start Premium holatini o'qiydi


def active_view(tier, days=10):
    """Faol Premium holati (ichki tarif kodi bilan)."""
    return bot.database.admin_premium_view(1, tier, bot.database.get_uz_now() + __import__("datetime").timedelta(days=days))


PRO_VIEW = active_view("pro")


class DeepLinkBase(unittest.TestCase):
    def run_start(self, param, has_discount, view=FREE_VIEW, env=None):
        message = mock.MagicMock()
        message.text = f"/start {param}"
        message.from_user = SimpleNamespace(id=USER_ID, first_name="Ali", last_name=None, username="ali")
        message.answer = mock.AsyncMock()
        message.answer_invoice = mock.AsyncMock()
        state = mock.MagicMock()
        state.clear = mock.AsyncMock()
        has_discount_mock = mock.MagicMock(return_value=has_discount)
        with mock.patch.dict(os.environ, env or {"PRO_MONTHLY_STARS": "150"}), \
             mock.patch.object(bot.database, "register_user"), \
             mock.patch.object(bot.database, "get_premium_view", return_value=view), \
             mock.patch.object(bot.database, "has_discount", has_discount_mock):
            asyncio.run(bot.cmd_start(message, state))
        return message, has_discount_mock


class DeepLinkDiscountTest(DeepLinkBase):
    def invoice(self, message):
        message.answer_invoice.assert_awaited_once()
        return message.answer_invoice.await_args.kwargs

    def test_discount_user_gets_discount_payload_and_half_price(self):
        message, _ = self.run_start("buy_plus_30", has_discount=True)
        kw = self.invoice(message)
        self.assertEqual(kw["payload"], bot.DISCOUNT_PAYLOAD)
        self.assertEqual(kw["prices"][0].amount, 75)
        self.assertEqual(kw["currency"], "XTR")
        self.assertIn("50% chegirma", kw["title"])
        # Foydalanuvchiga ko'rsatiladigan narx ham chegirmali
        self.assertIn("75 Telegram Stars", message.answer.await_args_list[0].args[0])

    def test_user_without_discount_gets_full_price(self):
        message, _ = self.run_start("buy_plus_30", has_discount=False)
        kw = self.invoice(message)
        self.assertEqual(kw["payload"], "PLUS_30_DAYS")
        self.assertEqual(kw["prices"][0].amount, 150)
        self.assertIn("150 Telegram Stars", message.answer.await_args_list[0].args[0])

    def test_price_follows_env(self):
        message, _ = self.run_start("buy_plus_30", has_discount=True, env={"PRO_MONTHLY_STARS": "200"})
        self.assertEqual(self.invoice(message)["prices"][0].amount, 100)

    def test_discount_does_not_apply_to_other_tariffs(self):
        for param, payload, price in (("buy_pro_7", "PRO_7_DAYS", 50), ("buy_ultra_30", "ULTRA_30_DAYS", 300)):
            with self.subTest(param=param):
                message, has_discount = self.run_start(param, has_discount=True,
                                                      env={"PRO_TRIAL_STARS": "50", "ULTRA_MONTHLY_STARS": "300"})
                kw = self.invoice(message)
                self.assertEqual((kw["payload"], kw["prices"][0].amount), (payload, price))
                has_discount.assert_not_called()          # chegirma tekshiruvi faqat Plus uchun

    def test_discount_still_respects_tier_eligibility(self):
        # Ultra (pastroq tarif sotib olinmaydi) chegirma bilan ham xarid qila olmaydi
        message, _ = self.run_start("buy_plus_30", has_discount=True, view=active_view("ultra"))
        message.answer_invoice.assert_not_awaited()
        self.assertIn("pastroq tarif sotib olinmaydi", message.answer.await_args.args[0])
        self.assertIn("Premium Ultra", message.answer.await_args.args[0])

    def test_active_plus_user_extends_with_discount(self):
        # Faol ichki plus (ko'rinadigan Pro) chegirmani uzaytirish sifatida ishlatadi
        message, _ = self.run_start("buy_plus_30", has_discount=True, view=active_view("plus"))
        kw = self.invoice(message)
        self.assertEqual((kw["payload"], kw["prices"][0].amount), (bot.DISCOUNT_PAYLOAD, 75))

    def test_pro_user_can_upgrade_to_plus_with_discount(self):
        message, _ = self.run_start("buy_plus_30", has_discount=True, view=PRO_VIEW)
        self.assertEqual(self.invoice(message)["payload"], bot.DISCOUNT_PAYLOAD)


class SharedOfferTest(unittest.TestCase):
    def test_discount_offer_is_validated_and_consumed_by_existing_payment_flow(self):
        with mock.patch.dict(os.environ, {"PRO_MONTHLY_STARS": "150"}):
            title, desc, payload, stars = bot.discount_plus_offer()
            self.assertEqual((payload, stars), (bot.DISCOUNT_PAYLOAD, 75))
            self.assertEqual(bot.validate_payment(payload, "XTR", stars), (True, ""))
            self.assertEqual(bot.validate_payment(payload, "XTR", 150), (False, "amount"))

    def test_inline_button_uses_same_offer(self):
        cb = mock.MagicMock()
        cb.data = "buy_plus_30_discount"
        cb.from_user = SimpleNamespace(id=USER_ID)
        cb.answer = mock.AsyncMock()
        cb.message.answer_invoice = mock.AsyncMock()
        with mock.patch.dict(os.environ, {"PRO_MONTHLY_STARS": "150"}), \
             mock.patch.object(bot.database, "get_premium_view", return_value=FREE_VIEW), \
             mock.patch.object(bot.database, "has_discount", return_value=True):
            asyncio.run(bot.process_pay_stars_tariff(cb))
            expected = bot.discount_plus_offer()
        kw = cb.message.answer_invoice.await_args.kwargs
        self.assertEqual((kw["title"], kw["description"], kw["payload"], kw["prices"][0].amount), expected)


if __name__ == "__main__":
    unittest.main()
