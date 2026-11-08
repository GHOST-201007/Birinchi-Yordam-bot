"""
test_miniapp_invoice_api.py — POST /api/invoice (Mini App ichida Premium sotib olish, Stars invoice link).

aiohttp serveri xotirada ishga tushiriladi; DB va Telegram mock qilinadi. Haqiqiy tarmoq/baza ishlatilmaydi.
"""
import contextlib
import datetime
import logging
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

from aiogram.exceptions import TelegramAPIError
from aiogram.methods import CreateInvoiceLink

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import bot  # noqa: E402
from tests.test_miniapp_api import ApiTestBase, USER_ID, OTHER_ID, fresh_init_data  # noqa: E402

LINK = "https://t.me/$AAH-test-invoice-link"
PRICES = {"buy_pro_7": ("PRO_7_DAYS", 50), "buy_plus_30": ("PLUS_30_DAYS", 150), "buy_ultra_30": ("ULTRA_30_DAYS", 300)}
FREE = {"is_premium": 0, "premium_type": "free"}


class InvoiceBase(ApiTestBase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        self.user_info = dict(FREE)
        self.discount = False
        self.get_user_info = mock.MagicMock(side_effect=lambda uid: self.user_info)
        self.has_discount = mock.MagicMock(side_effect=lambda uid: self.discount)
        self.create_link = mock.AsyncMock(return_value=LINK)
        stack.enter_context(mock.patch.object(bot.database, "get_user_info", self.get_user_info))
        stack.enter_context(mock.patch.object(bot.database, "has_discount", self.has_discount))
        stack.enter_context(mock.patch.object(bot, "bot", SimpleNamespace(create_invoice_link=self.create_link)))
        stack.enter_context(mock.patch.dict(os.environ, {
            "PRO_TRIAL_STARS": "50", "PRO_MONTHLY_STARS": "150", "ULTRA_MONTHLY_STARS": "300"}))

    async def invoice(self, plan, extra=None, init_data=None):
        body = {"plan": plan}
        body.update(extra or {})
        return await self.post("/api/invoice", init_data=init_data, extra=body)

    def link_kwargs(self):
        self.create_link.assert_awaited_once()
        return self.create_link.await_args.kwargs


class InvoiceEndpointTest(InvoiceBase):
    async def test_forged_init_data_403_and_nothing_called(self):
        good = fresh_init_data()
        bad = good[:-1] + ("0" if good[-1] != "0" else "1")
        resp, data = await self.invoice("buy_plus_30", init_data=bad)
        self.assertEqual(resp.status, 403)
        self.assertEqual(data, {"ok": False, "error": "forbidden"})
        self.create_link.assert_not_awaited()
        self.get_user_info.assert_not_called()
        self.has_discount.assert_not_called()
        self.assert_no_db_calls()

    async def test_bad_plan_400(self):
        for plan in ("", "BUY_PRO_7", "buy_pro_7 ", "buy_plus_30_discount", "pay_stars", "premium", "PLUS_30_DAYS",
                     5, True, ["buy_pro_7"], {"a": 1}, None):
            with self.subTest(plan=plan):
                resp, data = await self.invoice(plan)
                self.assertEqual(resp.status, 400)
                self.assertEqual(data, {"ok": False, "error": "bad_plan"})
        resp, data = await self.post("/api/invoice")           # plan umuman yo'q
        self.assertEqual((resp.status, data), (400, {"ok": False, "error": "bad_plan"}))
        self.create_link.assert_not_awaited()

    async def test_each_plan_returns_link_with_server_side_price_and_payload(self):
        for plan, (payload, stars) in PRICES.items():
            with self.subTest(plan=plan):
                self.create_link.reset_mock()
                resp, data = await self.invoice(plan)
                self.assertEqual(resp.status, 200)
                self.assertEqual(data, {"ok": True, "url": LINK})
                kw = self.link_kwargs()
                self.assertEqual(kw["payload"], payload)
                self.assertEqual(kw["currency"], "XTR")
                self.assertEqual(kw["provider_token"], "")
                self.assertEqual(len(kw["prices"]), 1)
                self.assertEqual(kw["prices"][0].amount, stars)
                self.assertEqual(kw["prices"][0].label, kw["title"])
                self.assertTrue(kw["title"] and kw["description"])

    async def test_discount_gives_discount_payload_and_half_price_for_plus_only(self):
        self.discount = True
        resp, data = await self.invoice("buy_plus_30")
        kw = self.link_kwargs()
        self.assertEqual(data, {"ok": True, "url": LINK})
        self.assertEqual(kw["payload"], bot.DISCOUNT_PAYLOAD)
        self.assertEqual(kw["prices"][0].amount, 75)
        self.assertIn("50% chegirma", kw["title"])
        # Pro va Ultra uchun chegirma qo'llanmaydi
        for plan in ("buy_pro_7", "buy_ultra_30"):
            self.create_link.reset_mock()
            await self.invoice(plan)
            self.assertEqual(self.link_kwargs()["payload"], PRICES[plan][0])

    async def test_no_discount_gives_full_price_plus(self):
        await self.invoice("buy_plus_30")
        kw = self.link_kwargs()
        self.assertEqual((kw["payload"], kw["prices"][0].amount), ("PLUS_30_DAYS", 150))

    async def test_price_follows_env(self):
        with mock.patch.dict(os.environ, {"PRO_MONTHLY_STARS": "200"}):
            self.discount = True
            await self.invoice("buy_plus_30")
        self.assertEqual(self.link_kwargs()["prices"][0].amount, 100)

    async def test_client_supplied_price_payload_and_user_are_ignored(self):
        extra = {"price": 1, "stars": 1, "amount": 1, "payload": "HACKED", "currency": "USD", "title": "free",
                 "user_id": OTHER_ID, "provider_token": "x", "prices": [{"amount": 1}], "discount": True}
        resp, data = await self.invoice("buy_plus_30", extra=extra)
        self.assertEqual(data, {"ok": True, "url": LINK})
        kw = self.link_kwargs()
        self.assertEqual((kw["payload"], kw["prices"][0].amount, kw["currency"], kw["provider_token"]),
                         ("PLUS_30_DAYS", 150, "XTR", ""))
        self.assertNotIn("free", kw["title"])
        self.get_user_info.assert_called_once_with(USER_ID)           # faqat initData'dagi foydalanuvchi
        self.has_discount.assert_called_once_with(USER_ID)

    async def test_not_eligible_returns_ok_false_with_plain_message(self):
        cases = [
            ({"is_premium": 1, "premium_type": "plus"}, "buy_pro_7", "Premium Plus"),
            ({"is_premium": 1, "premium_type": "plus"}, "buy_plus_30", "Premium Plus"),
            ({"is_premium": 1, "premium_type": "ultra"}, "buy_ultra_30", "Premium Ultra"),
            ({"is_premium": 1, "premium_type": "pro"}, "buy_pro_7", "Premium Pro"),
        ]
        for info, plan, tier in cases:
            with self.subTest(info=info["premium_type"], plan=plan):
                self.user_info = info
                resp, data = await self.invoice(plan)
                self.assertEqual(resp.status, 200)
                self.assertEqual(data["ok"], False)
                self.assertEqual(data["error"], "not_eligible")
                self.assertIn(tier, data["message"])
                self.assertNotIn("<", data["message"])                   # oddiy matn
        self.create_link.assert_not_awaited()

    async def test_discount_does_not_bypass_eligibility(self):
        self.user_info = {"is_premium": 1, "premium_type": "plus"}
        self.discount = True
        resp, data = await self.invoice("buy_plus_30")
        self.assertEqual(data["error"], "not_eligible")
        self.create_link.assert_not_awaited()

    async def test_pro_user_can_upgrade_to_plus(self):
        self.user_info = {"is_premium": 1, "premium_type": "pro"}
        resp, data = await self.invoice("buy_plus_30")
        self.assertEqual(data, {"ok": True, "url": LINK})

    async def test_banned_user_403(self):
        self.m["banned"].return_value = (True, "ban")
        resp, data = await self.invoice("buy_pro_7")
        self.assertEqual((resp.status, data), (403, {"ok": False, "error": "banned"}))
        self.create_link.assert_not_awaited()

    async def test_rate_limit_shared_with_other_endpoints(self):
        for _ in range(19):
            await self.post("/api/state")
        resp, _ = await self.invoice("buy_pro_7")
        self.assertEqual(resp.status, 200)                               # 20-so'rov
        resp, data = await self.invoice("buy_pro_7")
        self.assertEqual((resp.status, data), (429, {"ok": False, "error": "rate_limited"}))

    async def test_only_post_json_and_size_limit(self):
        for method in ("get", "put", "delete"):
            resp = await getattr(self.client, method)("/api/invoice")
            self.assertEqual(resp.status, 405)
        resp, _ = await self.post("/api/invoice", raw='{"init_data":"x"}', content_type="text/plain")
        self.assertEqual(resp.status, 415)
        resp, data = await self.invoice("buy_pro_7", extra={"pad": "x" * 5000})
        self.assertEqual((resp.status, data), (413, {"ok": False, "error": "payload_too_large"}))

    async def test_telegram_error_gives_generic_500_without_details_or_init_data_in_logs(self):
        marker = "LOG-MARKER-FIRSTNAME"
        init = fresh_init_data(user={"id": USER_ID, "first_name": marker})
        method = CreateInvoiceLink(title="t", description="d", payload="p", currency="XTR", prices=[])
        self.create_link.side_effect = TelegramAPIError(method, "Bad Request: SECRET-DETAIL token=123:ABC")
        with self.assertLogs(level="DEBUG") as logs:
            resp, data = await self.invoice("buy_pro_7", init_data=init)
        self.assertEqual((resp.status, data), (500, {"ok": False, "error": "server_error"}))
        joined = "\n".join(logs.output)
        self.assertIn("API invoice xatosi", joined)
        self.assertNotIn(marker, joined)
        self.assertNotIn(init, joined)
        self.assertNotIn("SECRET-DETAIL", str(data))

    async def test_existing_endpoints_response_format_unchanged(self):
        resp, data = await self.post("/api/state")
        # Avvalgi maydonlar o'zgarmagan; header uchun faqat is_premium va premium_type QO'SHILGAN
        self.assertEqual(sorted(data), ["cooldown_seconds", "daily_claimed", "is_premium", "ok", "premium_type",
                                        "prize", "score", "streak"])
        resp, data = await self.post("/api/spin/claim")
        self.assertEqual(sorted(data), ["is_super", "message", "ok", "score"])
        resp, data = await self.post("/api/bonus/claim")
        self.assertEqual(sorted(data), ["message", "ok", "points", "score", "streak"])

    async def test_route_registered_with_api_prefix(self):
        paths = {r.canonical for r in self.client.app.router.resources()}
        self.assertIn("/api/invoice", paths)
        self.assertNotIn("/invoice", paths)


class InvoiceVsPaymentHandlersTest(InvoiceBase):
    """Invoice link orqali to'lov ham MAVJUD handlerlarga keladi (ular o'zgarmagan): API bergan parametrlar
    validate_payment, process_pre_checkout va process_successful_payment dan o'tadi."""

    async def api_offer(self, plan, discount=False):
        self.discount = discount
        self.create_link.reset_mock()
        resp, data = await self.invoice(plan)
        self.assertTrue(data.get("ok"), data)
        kw = self.link_kwargs()
        return kw["payload"], kw["prices"][0].amount, kw["currency"]

    def pre_checkout(self, payload, amount, currency):
        q = mock.MagicMock()
        q.from_user = SimpleNamespace(id=USER_ID)
        q.invoice_payload = payload
        q.total_amount = amount
        q.currency = currency
        q.answer = mock.AsyncMock()
        return q

    def paid_message(self, payload, amount, currency, charge="charge_test_1"):
        msg = mock.MagicMock()
        msg.from_user = SimpleNamespace(id=USER_ID, username="ali")
        msg.successful_payment = SimpleNamespace(
            invoice_payload=payload, total_amount=amount, currency=currency,
            telegram_payment_charge_id=charge, provider_payment_charge_id=None)
        msg.answer = mock.AsyncMock()
        msg.bot = SimpleNamespace(send_message=mock.AsyncMock())
        return msg

    async def test_api_offers_pass_validate_pre_checkout_and_successful_payment(self):
        until = datetime.datetime(2026, 12, 1, tzinfo=datetime.timezone.utc)
        scenarios = [(plan, False) for plan in PRICES] + [("buy_plus_30", True)]
        for plan, discount in scenarios:
            with self.subTest(plan=plan, discount=discount):
                payload, stars, currency = await self.api_offer(plan, discount)

                self.assertEqual(bot.validate_payment(payload, currency, stars), (True, ""))

                query = self.pre_checkout(payload, stars, currency)
                self.discount = discount
                await bot.process_pre_checkout(query)
                self.assertTrue(query.answer.await_args.kwargs["ok"], "pre_checkout API invoysini rad etdi")

                paid = mock.MagicMock(return_value=(True, until))
                msg = self.paid_message(payload, stars, currency)
                with mock.patch.object(bot.database, "process_paid_premium", paid):
                    await bot.process_successful_payment(msg)
                paid.assert_called_once()
                args = paid.call_args.args
                self.assertEqual(args[0:4], ("charge_test_1", USER_ID, payload, stars))
                self.assertEqual(args[-1], payload == bot.DISCOUNT_PAYLOAD)   # chegirma FAQAT to'lov bilan sarflanadi
                msg.answer.assert_awaited()

    async def test_discount_invoice_rejected_by_pre_checkout_once_discount_is_used(self):
        payload, stars, currency = await self.api_offer("buy_plus_30", discount=True)
        self.assertEqual((payload, stars), (bot.DISCOUNT_PAYLOAD, 75))
        self.discount = False                          # chegirma boshqa yo'l bilan allaqachon sarflangan
        query = self.pre_checkout(payload, stars, currency)
        await bot.process_pre_checkout(query)
        self.assertFalse(query.answer.await_args.kwargs["ok"])

    async def test_tampered_amount_for_api_invoice_is_rejected(self):
        payload, stars, currency = await self.api_offer("buy_plus_30", discount=False)
        self.assertEqual(bot.validate_payment(payload, currency, stars - 1), (False, "amount"))
        self.assertEqual(bot.validate_payment(payload, "USD", stars), (False, "currency"))


class BuildOfferUnitTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.discount = False
        patcher = mock.patch.object(bot.database, "has_discount", side_effect=lambda uid: self.discount)
        self.has_discount = patcher.start()
        self.addCleanup(patcher.stop)
        env = mock.patch.dict(os.environ, {"PRO_TRIAL_STARS": "50", "PRO_MONTHLY_STARS": "150", "ULTRA_MONTHLY_STARS": "300"})
        env.start()
        self.addCleanup(env.stop)

    async def test_offers_match_previous_inline_values(self):
        pro = await bot.build_premium_offer(1, "buy_pro_7")
        self.assertEqual(pro[2:], ("PRO_7_DAYS", 50))
        self.assertEqual(pro[0], "⭐ Premium Pro — 7 kun")
        self.assertEqual((await bot.build_premium_offer(1, "pay_stars"))[2:], ("PRO_7_DAYS", 50))     # callback taxallusi
        self.assertEqual((await bot.build_premium_offer(1, "buy_plus_30"))[2:], ("PLUS_30_DAYS", 150))
        self.assertEqual((await bot.build_premium_offer(1, "buy_ultra_30"))[2:], ("ULTRA_30_DAYS", 300))

    async def test_discount_variants(self):
        self.discount = True
        self.assertEqual((await bot.build_premium_offer(1, "buy_plus_30"))[2:], (bot.DISCOUNT_PAYLOAD, 75))
        self.assertEqual((await bot.build_premium_offer(1, "buy_plus_30_discount"))[2:], (bot.DISCOUNT_PAYLOAD, 75))
        self.assertEqual((await bot.build_premium_offer(1, "buy_pro_7"))[2:], ("PRO_7_DAYS", 50))

    async def test_discount_button_without_discount_is_unavailable(self):
        with self.assertRaises(bot.OfferUnavailable) as ctx:
            await bot.build_premium_offer(1, "buy_plus_30_discount")
        self.assertEqual(ctx.exception.code, "no_discount")

    async def test_unknown_plan_is_unavailable(self):
        for action in ("", "x", "BUY_PRO_7", None):
            with self.subTest(action=action):
                with self.assertRaises(bot.OfferUnavailable) as ctx:
                    await bot.build_premium_offer(1, action)
                self.assertEqual(ctx.exception.code, "bad_plan")

    async def test_non_positive_price_is_rejected(self):
        with mock.patch.dict(os.environ, {"PRO_TRIAL_STARS": "0"}):
            with self.assertRaises(ValueError):
                await bot.build_premium_offer(1, "buy_pro_7")


if __name__ == "__main__":
    unittest.main()
