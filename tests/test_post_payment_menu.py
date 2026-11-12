"""
test_post_payment_menu.py — to'lovdan (va 100 ball / baraban 1 kunlik Premium sovrinidan) KEYIN menyu darhol yangilanadi:
  * tasdiq xabariga yangi holatdagi reply klaviatura qo'shiladi (pastdagi tugma darhol "👑 Premium Ultra" kabi bo'ladi);
  * menyu keshi yangilanadi;
  * shaxsiy "👑 Ilova" tugmasi fonda qo'yiladi (schedule_personal_menu_sync);
  * bir xil tarif uzaytirilganda: "✅ Premium Ultra 30 kunga uzaytirildi — yangi tugash sanasi: 11.01.2027".
To'lov mantig'i (summa, payload, process_paid_premium argumentlari, takroriy to'lov, reconcile) o'zgarmagan.
Telegram va haqiqiy baza ishlatilmaydi.
"""
import datetime as dt
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

UZ = dt.timezone(dt.timedelta(hours=5))
NOW = dt.datetime(2026, 11, 12, 12, 0, tzinfo=UZ)
UID = 900000951
ENV = {"PRO_TRIAL_STARS": "50", "PRO_MONTHLY_STARS": "150", "ULTRA_MONTHLY_STARS": "300"}
PAYLOADS = {"pro": ("PRO_7_DAYS", 50, 7), "plus": ("PLUS_30_DAYS", 150, 30), "ultra": ("ULTRA_30_DAYS", 300, 30)}
RANK = {"free": 0, "pro": 1, "plus": 2, "ultra": 3}


def active(tier, until):
    return database.admin_premium_view(1, tier, until.isoformat(), NOW)


def free():
    return database.admin_premium_view(0, None, None, NOW)


def keyboard_labels(markup):
    return [b.text for row in markup.keyboard for b in row]


def premium_label(markup):
    found = [t for t in keyboard_labels(markup) if "Premium" in t]
    assert len(found) == 1, found
    return found[0]


def reset_caches():
    bot._menu_reset_done.clear()
    bot._menu_premium_done.clear()
    bot._premium_menu_cache.clear()


class PaymentBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        reset_caches()
        self.addCleanup(reset_caches)
        env = mock.patch.dict(os.environ, ENV)
        env.start()
        self.addCleanup(env.stop)
        self.sync = mock.MagicMock()
        patcher = mock.patch.object(bot, "schedule_personal_menu_sync", self.sync)
        patcher.start()
        self.addCleanup(patcher.stop)

    def paid_message(self, payload, stars, charge="charge_pp_1"):
        msg = mock.MagicMock()
        msg.from_user = SimpleNamespace(id=UID, username="ali")
        msg.successful_payment = SimpleNamespace(
            invoice_payload=payload, total_amount=stars, currency="XTR",
            telegram_payment_charge_id=charge, provider_payment_charge_id=None)
        msg.answer = mock.AsyncMock()
        msg.bot = SimpleNamespace(send_message=mock.AsyncMock())
        return msg

    async def pay(self, tier, before, after, until, granted=True, views_fail=False, charge="charge_pp_1"):
        """to'lov oqimini yurgizadi. before / after — to'lovdan oldingi va keyingi (bazadagi) holat."""
        payload, stars, days = PAYLOADS[tier]
        msg = self.paid_message(payload, stars, charge)
        if views_fail:
            views = mock.MagicMock(side_effect=RuntimeError("baza uzildi"))
        else:
            views = mock.MagicMock(side_effect=[before, after])
        self.paid = mock.MagicMock(return_value=(granted, until if granted else None))
        with mock.patch.object(database, "get_premium_view", views), \
                mock.patch.object(database, "process_paid_premium", self.paid):
            await bot.process_successful_payment(msg)
        self.views = views
        return msg


class KeyboardAfterPaymentTest(PaymentBase):
    async def test_confirmation_has_the_new_tier_button(self):
        until = NOW + dt.timedelta(days=30)
        cases = [
            # (sotib olingan, avval, keyin, kutilgan tugma)
            ("pro", free(), active("pro", NOW + dt.timedelta(days=7)), "⭐ Premium Plus"),
            ("plus", free(), active("plus", until), "💎 Premium Pro"),
            ("ultra", free(), active("ultra", until), "👑 Premium Ultra"),
            ("plus", active("pro", NOW + dt.timedelta(days=3)), active("plus", until), "💎 Premium Pro"),      # upgrade
            ("ultra", active("plus", NOW + dt.timedelta(days=3)), active("ultra", until), "👑 Premium Ultra"),
        ]
        for tier, before, after, label in cases:
            with self.subTest(buy=tier, before=before["tier"]):
                reset_caches()
                msg = await self.pay(tier, before, after, until, charge=f"c_{tier}_{before['tier']}")
                markup = msg.answer.await_args_list[0].kwargs["reply_markup"]
                self.assertEqual(premium_label(markup), label)
                self.assertIn("To'lov muvaffaqiyatli qabul qilindi", msg.answer.await_args_list[0].args[0])
                self.assertNotIn("uzaytirildi", msg.answer.await_args_list[0].args[0])        # bu — yangi xarid/upgrade

    async def test_menu_cache_is_refreshed(self):
        bot.remember_premium_state(UID, free())                                    # eski kesh: Premium yo'q
        until = NOW + dt.timedelta(days=30)
        await self.pay("ultra", free(), active("ultra", until), until)
        self.assertEqual(bot.cached_premium_view(UID), {"active": True, "tier": "ultra"})
        self.assertEqual(premium_label(bot.get_start_keyboard_for(UID)), "👑 Premium Ultra")   # keyingi javoblarda ham

    async def test_personal_app_button_is_set_in_the_background(self):
        until = NOW + dt.timedelta(days=30)
        msg = await self.pay("plus", free(), active("plus", until), until)
        self.sync.assert_called_once_with(msg.bot, UID, True)

    async def test_payment_logic_is_unchanged(self):
        until = NOW + dt.timedelta(days=30)
        await self.pay("ultra", free(), active("ultra", until), until, charge="charge_args")
        self.paid.assert_called_once_with("charge_args", UID, "ULTRA_30_DAYS", 300, "ultra", 30, False)

    async def test_discount_payment_still_consumes_discount_and_shows_pro(self):
        until = NOW + dt.timedelta(days=30)
        msg = self.paid_message(bot.DISCOUNT_PAYLOAD, 75, "charge_disc")
        paid = mock.MagicMock(return_value=(True, until))
        with mock.patch.object(database, "get_premium_view", mock.MagicMock(side_effect=[free(), active("plus", until)])), \
                mock.patch.object(database, "process_paid_premium", paid):
            await bot.process_successful_payment(msg)
        paid.assert_called_once_with("charge_disc", UID, bot.DISCOUNT_PAYLOAD, 75, "plus", 30, True)
        self.assertEqual(premium_label(msg.answer.await_args_list[0].kwargs["reply_markup"]), "💎 Premium Pro")


class ExtensionMessageTest(PaymentBase):
    async def test_same_tier_says_extended_with_new_expiry(self):
        before = active("ultra", dt.datetime(2026, 12, 12, 12, 0, tzinfo=UZ))
        until = dt.datetime(2027, 1, 11, 12, 0, tzinfo=UZ)
        msg = await self.pay("ultra", before, active("ultra", until), until)
        text = msg.answer.await_args_list[0].args[0]
        self.assertIn("✅ Premium Ultra 30 kunga uzaytirildi — yangi tugash sanasi: 11.01.2027", text)
        self.assertNotIn("To'lov muvaffaqiyatli qabul qilindi", text)
        self.assertEqual(premium_label(msg.answer.await_args_list[0].kwargs["reply_markup"]), "👑 Premium Ultra")
        self.assertEqual(msg.answer.await_args_list[0].kwargs["parse_mode"], "HTML")

    async def test_each_tier_extension_text_uses_visible_name_and_days(self):
        for tier, name, days in (("pro", "Plus", 7), ("plus", "Pro", 30), ("ultra", "Ultra", 30)):
            with self.subTest(tier=tier):
                until = NOW + dt.timedelta(days=days + 3)
                msg = await self.pay(tier, active(tier, NOW + dt.timedelta(days=3)), active(tier, until), until,
                                     charge=f"ext_{tier}")
                text = msg.answer.await_args_list[0].args[0]
                self.assertIn(f"✅ Premium {name} {days} kunga uzaytirildi — yangi tugash sanasi: "
                              f"{until:%d.%m.%Y}", text)

    async def test_upgrade_and_new_purchase_are_not_called_extension(self):
        until = NOW + dt.timedelta(days=30)
        msg = await self.pay("ultra", active("plus", NOW + dt.timedelta(days=3)), active("ultra", until), until)
        self.assertNotIn("uzaytirildi", msg.answer.await_args_list[0].args[0])
        msg = await self.pay("plus", free(), active("plus", until), until, charge="new_1")
        self.assertNotIn("uzaytirildi", msg.answer.await_args_list[0].args[0])

    async def test_expired_premium_counts_as_new_purchase(self):
        expired = database.admin_premium_view(1, "ultra", (NOW - dt.timedelta(days=1)).isoformat(), NOW)
        until = NOW + dt.timedelta(days=30)
        msg = await self.pay("ultra", expired, active("ultra", until), until)
        self.assertIn("To'lov muvaffaqiyatli qabul qilindi", msg.answer.await_args_list[0].args[0])


class RobustnessTest(PaymentBase):
    async def test_payment_succeeds_even_if_state_cannot_be_read_after(self):
        until = NOW + dt.timedelta(days=30)
        views = mock.MagicMock(side_effect=[free(), RuntimeError("baza uzildi")])
        msg = self.paid_message("PLUS_30_DAYS", 150)
        paid = mock.MagicMock(return_value=(True, until))
        with mock.patch.object(database, "get_premium_view", views), \
                mock.patch.object(database, "process_paid_premium", paid):
            await bot.process_successful_payment(msg)
        paid.assert_called_once()
        # DB o'qilmadi: to'lov va yangi holat hisoblangan qiymatdan ko'rsatiladi
        self.assertEqual(premium_label(msg.answer.await_args_list[0].kwargs["reply_markup"]), "💎 Premium Pro")
        self.sync.assert_called_once_with(msg.bot, UID, True)

    async def test_payment_succeeds_when_state_cannot_be_read_at_all(self):
        until = NOW + dt.timedelta(days=30)
        bot.remember_premium_state(UID, active("pro", until))                       # eskirgan kesh bo'lishi mumkin
        msg = await self.pay("plus", None, None, until, views_fail=True)
        self.paid.assert_called_once()                                              # to'lov baribir qayta ishlandi
        text = msg.answer.await_args_list[0].args[0]
        self.assertIn("To'lov muvaffaqiyatli qabul qilindi", text)                  # uzaytirildi deb ayta olmaymiz
        self.assertEqual(premium_label(msg.answer.await_args_list[0].kwargs["reply_markup"]), "💎 Premium Pro")

    async def test_duplicate_payment_is_rejected_without_menu_changes(self):
        msg = await self.pay("ultra", free(), free(), None, granted=False, charge="dup")
        self.assertIn("allaqachon qayta ishlangan", msg.answer.await_args.args[0])
        self.sync.assert_not_called()

    async def test_db_error_does_not_touch_the_menu(self):
        msg = self.paid_message("PLUS_30_DAYS", 150)
        with mock.patch.object(database, "get_premium_view", mock.MagicMock(return_value=free())), \
                mock.patch.object(database, "process_paid_premium", mock.MagicMock(side_effect=RuntimeError("x"))), \
                mock.patch.object(bot, "record_failed_payment", mock.MagicMock(return_value=True)):
            await bot.process_successful_payment(msg)
        self.sync.assert_not_called()
        self.assertIn("vaqtinchalik xatolik", msg.answer.await_args.args[0])

    async def test_wrong_amount_is_rejected_before_anything_happens(self):
        msg = self.paid_message("PLUS_30_DAYS", 149)
        paid = mock.MagicMock()
        with mock.patch.object(database, "get_premium_view", mock.MagicMock(return_value=free())), \
                mock.patch.object(database, "process_paid_premium", paid):
            await bot.process_successful_payment(msg)
        paid.assert_not_called()
        self.sync.assert_not_called()


class RedeemTest(PaymentBase):
    def callback(self):
        cb = mock.MagicMock()
        cb.from_user = SimpleNamespace(id=UID)
        cb.answer = mock.AsyncMock()
        cb.message.answer = mock.AsyncMock()
        cb.message.edit_text = mock.AsyncMock()
        cb.bot = SimpleNamespace()
        return cb

    async def test_redeem_sends_new_keyboard_and_updates_menu(self):
        cb = self.callback()
        after = active("pro", NOW + dt.timedelta(days=3))
        with mock.patch.object(database, "check_and_grant_premium", return_value=True), \
                mock.patch.object(database, "get_premium_view", mock.MagicMock(side_effect=[free(), after, after])), \
                mock.patch.object(bot, "_show_premium_page", mock.AsyncMock()) as page:
            await bot.process_redeem_points_premium(cb)
        self.assertIn("3 kunlik Premium Plus", cb.answer.await_args.args[0])
        page.assert_awaited_once()
        sent = cb.message.answer.await_args
        self.assertIn("⭐ Premium Plus faol", sent.args[0])
        self.assertEqual(premium_label(sent.kwargs["reply_markup"]), "⭐ Premium Plus")
        self.sync.assert_called_once_with(cb.bot, UID, True)
        self.assertEqual(bot.cached_premium_view(UID), {"active": True, "tier": "pro"})

    async def test_redeem_keeps_higher_tier_on_the_keyboard(self):
        cb = self.callback()
        after = active("ultra", NOW + dt.timedelta(days=13))
        with mock.patch.object(database, "check_and_grant_premium", return_value=True), \
                mock.patch.object(database, "get_premium_view", mock.MagicMock(side_effect=[after, after, after])), \
                mock.patch.object(bot, "_show_premium_page", mock.AsyncMock()):
            await bot.process_redeem_points_premium(cb)
        self.assertEqual(premium_label(cb.message.answer.await_args.kwargs["reply_markup"]), "👑 Premium Ultra")

    async def test_redeem_with_unlimited_premium_is_refused_and_points_stay(self):
        cb = self.callback()
        unlimited = database.admin_premium_view(1, "ultra", None, NOW)
        grant = mock.MagicMock()
        with mock.patch.object(database, "check_and_grant_premium", grant), \
                mock.patch.object(database, "get_premium_view", mock.MagicMock(return_value=unlimited)):
            await bot.process_redeem_points_premium(cb)
        grant.assert_not_called()                               # ballar yechilmaydi, muddatsiz Premium buzilmaydi
        self.assertIn("muddatsiz Premium", cb.answer.await_args.args[0])
        self.sync.assert_not_called()

    async def test_failed_redeem_changes_nothing(self):
        cb = self.callback()
        with mock.patch.object(database, "check_and_grant_premium", return_value=False), \
                mock.patch.object(database, "get_premium_view", mock.MagicMock(return_value=free())), \
                mock.patch.object(database, "get_score", return_value=40):
            await bot.process_redeem_points_premium(cb)
        cb.message.answer.assert_not_awaited()
        self.sync.assert_not_called()
        self.assertIn("yetarli emas", cb.answer.await_args.args[0])


class WheelProDayTest(PaymentBase):
    def start_message(self, text="/start spin_proday"):
        message = mock.MagicMock()
        message.text = text
        message.from_user = SimpleNamespace(id=UID, first_name="Ali", last_name=None, username="ali")
        message.answer = mock.AsyncMock()
        message.bot = SimpleNamespace()
        return message

    async def run_start(self, message, views, claim):
        state = mock.MagicMock()
        state.clear = mock.AsyncMock()
        with mock.patch.object(database, "register_user"), \
                mock.patch.object(database, "claim_spin_prize", return_value=claim), \
                mock.patch.object(database, "get_premium_view", mock.MagicMock(side_effect=views)):
            await bot.cmd_start(message, state)

    async def test_spin_deep_link_pro_day_refreshes_keyboard_and_button(self):
        message = self.start_message()
        after = active("pro", NOW + dt.timedelta(days=1))
        claim = {"ok": True, "message": "⭐ 1 kunlik Premium Plus yutdingiz", "prize_type": "pro_day", "code": -3}
        await self.run_start(message, [free(), after], claim)
        markup = message.answer.await_args.kwargs["reply_markup"]
        self.assertEqual(premium_label(markup), "⭐ Premium Plus")                  # darhol yangi tugma
        self.assertEqual(bot.cached_premium_view(UID), {"active": True, "tier": "pro"})
        # /start boshida bir marta (bepul holat), sovrindan keyin yana bir marta (Premium) — shaxsiy tugma fonda
        self.assertEqual([c.args[1:] for c in self.sync.call_args_list], [(UID, False), (UID, True)])

    async def test_other_prizes_do_not_refresh(self):
        message = self.start_message("/start spin_5")
        claim = {"ok": True, "message": "+5 ball", "prize_type": "points", "code": 5}
        await self.run_start(message, [free()], claim)
        self.assertEqual(premium_label(message.answer.await_args.kwargs["reply_markup"]), "💎 Premium")
        self.assertEqual([c.args[1:] for c in self.sync.call_args_list], [(UID, False)])

    async def test_api_claim_pro_day_updates_cache_and_personal_button(self):
        after = active("pro", NOW + dt.timedelta(days=1))
        claim = {"ok": True, "message": "1 kunlik Premium Plus", "prize_type": "pro_day", "code": -3,
                 "points": 0, "tip": None}
        with mock.patch.object(database, "claim_spin_prize", return_value=claim), \
                mock.patch.object(database, "get_score", return_value=7), \
                mock.patch.object(database, "get_premium_view", mock.MagicMock(return_value=after)), \
                mock.patch.object(database, "get_ai_quota_detail", return_value=(14, 15, 0)):
            result = await bot._api_spin_claim_action(UID)
        self.assertTrue(result["is_premium"])
        self.assertEqual(result["premium_type"], "pro")
        self.sync.assert_called_once_with(bot.bot, UID, True)
        self.assertEqual(bot.cached_premium_view(UID), {"active": True, "tier": "pro"})

    async def test_api_claim_points_prize_leaves_menu_alone(self):
        claim = {"ok": True, "message": "+5 ball", "prize_type": "points", "code": 5, "points": 5, "tip": None}
        with mock.patch.object(database, "claim_spin_prize", return_value=claim), \
                mock.patch.object(database, "get_score", return_value=12):
            await bot._api_spin_claim_action(UID)
        self.sync.assert_not_called()


class ExtendButtonListTest(unittest.IsolatedAsyncioTestCase):
    """"Mening obunam" va "🔄 Uzaytirish" sahifasi: faqat sotib olish mumkin bo'lgan tariflar tugmasi."""

    async def pages(self, view, discount=False, score=7):
        target = mock.MagicMock()
        target.from_user = SimpleNamespace(id=UID)
        target.answer = mock.AsyncMock()
        with mock.patch.dict(os.environ, {**ENV, "MINI_APP_URL": "https://app.example/index.html"}), \
                mock.patch.object(database, "get_score", return_value=score), \
                mock.patch.object(database, "has_discount", return_value=discount), \
                mock.patch.object(bot, "get_web_app_url", mock.AsyncMock(return_value="https://x/app")):
            await bot._show_premium_sales(target, view)
        args, kwargs = target.answer.await_args
        return args[0], [(b.text, b.callback_data) for row in kwargs["reply_markup"].inline_keyboard for b in row
                         if b.callback_data and b.callback_data.startswith(("buy_", "premium_"))]

    async def test_ultra_sees_only_its_own_extension_button(self):
        text, buttons = await self.pages(active("ultra", NOW + dt.timedelta(days=5)))
        self.assertEqual(buttons, [("🔄 Premium Ultra — yana 30 kun (300 ⭐)", "buy_ultra_30")])
        self.assertIn("PREMIUMNI UZAYTIRISH", text)
        self.assertNotIn("PREMIUM PRO", text)
        self.assertNotIn("PREMIUM PLUS", text)

    async def test_pro_sees_its_extension_and_ultra_only(self):
        _text, buttons = await self.pages(active("plus", NOW + dt.timedelta(days=5)))
        self.assertEqual(buttons, [("🔄 Premium Pro — yana 30 kun (150 ⭐)", "buy_plus_30"),
                                   ("👑 300 Stars → 30 kun Premium Ultra", "buy_ultra_30")])

    async def test_plus_sees_all_three_with_its_own_as_extension(self):
        _text, buttons = await self.pages(active("pro", NOW + dt.timedelta(days=2)))
        self.assertEqual(buttons, [("🔄 Premium Plus — yana 7 kun (50 ⭐)", "buy_pro_7"),
                                   ("💎 150 Stars → 30 kun Premium Pro", "buy_plus_30"),
                                   ("👑 300 Stars → 30 kun Premium Ultra", "buy_ultra_30")])

    async def test_unlimited_premium_has_no_purchase_buttons(self):
        text, buttons = await self.pages(database.admin_premium_view(1, "ultra", None, NOW))
        self.assertEqual(buttons, [])
        self.assertIn("Sizda muddatsiz Premium bor", text)

    async def test_discount_button_for_active_plus_is_an_extension(self):
        _text, buttons = await self.pages(active("plus", NOW + dt.timedelta(days=5)), discount=True)
        self.assertEqual(buttons[0], ("🎁 Premium Pro — yana 30 kun (75 ⭐, -50%)", "buy_plus_30_discount"))
        _text, buttons = await self.pages(active("ultra", NOW + dt.timedelta(days=5)), discount=True)
        self.assertNotIn("buy_plus_30_discount", [b[1] for b in buttons])

    async def test_extend_callback_for_unlimited_shows_an_alert_only(self):
        cb = mock.MagicMock()
        cb.from_user = SimpleNamespace(id=UID)
        cb.answer = mock.AsyncMock()
        cb.message.edit_text = mock.AsyncMock()
        with mock.patch.object(database, "get_premium_view", return_value=database.admin_premium_view(1, "plus", None, NOW)):
            await bot.process_premium_extend(cb)
        self.assertIn("muddatsiz Premium", cb.answer.await_args.args[0])
        self.assertTrue(cb.answer.await_args.kwargs["show_alert"])
        cb.message.edit_text.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
