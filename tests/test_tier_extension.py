"""
test_tier_extension.py — bir xil tarifni qayta sotib olish = muddatni UZAYTIRISH.

Qoida (bot.premium_purchase_decision — YAGONA funksiya): faol Premiumda joriy tarif (uzaytirish) va undan yuqorilari
sotib olinadi; pastroq tarif — taqiq; muddatsiz Premium — taqiq (unga muddat qo'shib bo'lmaydi); muddati o'tgan flag —
oddiy foydalanuvchi. Bot tugmalari, Mini App /api/invoice va pre_checkout_query bir xil natija beradi.
Muddat qo'shilishi HAQIQIY SQL bilan (tests/sqlite_db.py) tasdiqlanadi. Telegram va haqiqiy baza ishlatilmaydi.
"""
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
from tests.ban_shim import not_banned_patch  # noqa: E402
from tests.sqlite_db import SqliteDB  # noqa: E402

UZ = dt.timezone(dt.timedelta(hours=5))
NOW = dt.datetime(2026, 11, 12, 12, 0, tzinfo=UZ)
USER_ID = 900000901
LINK = "https://t.me/$AAH-extension-link"
ENV = {"PRO_TRIAL_STARS": "50", "PRO_MONTHLY_STARS": "150", "ULTRA_MONTHLY_STARS": "300"}
RANK = {"free": 0, "pro": 1, "plus": 2, "ultra": 3}

# ichki tarif -> (API / tugma tarifi, payload, narx)
PLANS = {"pro": ("buy_pro_7", "PRO_7_DAYS", 50), "plus": ("buy_plus_30", "PLUS_30_DAYS", 150),
         "ultra": ("buy_ultra_30", "ULTRA_30_DAYS", 300)}


def state(kind, tier=None):
    """kind: free | expired | active | unlimited."""
    if kind == "free":
        return database.admin_premium_view(0, None, None, NOW)
    if kind == "expired":
        return database.admin_premium_view(1, tier, (NOW - dt.timedelta(days=1)).isoformat(), NOW)
    if kind == "unlimited":
        return database.admin_premium_view(1, tier, None, NOW)
    return database.admin_premium_view(1, tier, (NOW + dt.timedelta(days=10)).isoformat(), NOW)


STATES = ([("free", None)] + [("expired", t) for t in PLANS] + [("active", t) for t in PLANS]
          + [("unlimited", t) for t in PLANS])


def expected(kind, tier, buying):
    """(ruxsat, uzaytirish)."""
    if kind in ("free", "expired"):
        return True, False
    if kind == "unlimited":
        return False, False
    return RANK[tier] <= RANK[buying], tier == buying


def refusal(kind, tier):
    if kind == "unlimited":
        return "Sizda muddatsiz Premium bor — unga muddat qo'shib bo'lmaydi."
    return f"Sizda yuqoriroq tarif (Premium {database.TIER_DISPLAY[tier]}) bor — pastroq tarif sotib olinmaydi"


# ───────────────────────────── qoida (sof funksiya) ─────────────────────────────
class DecisionTest(unittest.TestCase):
    def test_full_matrix(self):
        for kind, tier in STATES:
            view = state(kind, tier)
            for buying, (action, _payload, _stars) in PLANS.items():
                with self.subTest(state=f"{kind}:{tier}", buying=buying):
                    allowed, extension = expected(kind, tier, buying)
                    decision = bot.premium_purchase_decision(view, buying)
                    self.assertEqual((decision.allowed, decision.extension), (allowed, extension))
                    ok, reason = bot.check_premium_purchase_eligibility(view, action)
                    self.assertEqual(ok, allowed)
                    if allowed:
                        self.assertIsNone(reason)
                    else:
                        self.assertTrue(reason.startswith(refusal(kind, tier)), reason)

    def test_task_examples(self):
        ultra = state("active", "ultra")
        self.assertEqual(bot.check_premium_purchase_eligibility(ultra, "buy_ultra_30"), (True, None))   # Ultra -> Ultra
        self.assertEqual(bot.check_premium_purchase_eligibility(state("active", "pro"), "buy_pro_7"), (True, None))
        self.assertEqual(bot.check_premium_purchase_eligibility(state("active", "plus"), "buy_ultra_30"), (True, None))
        self.assertEqual(bot.check_premium_purchase_eligibility(ultra, "buy_plus_30"),
                         (False, "Sizda yuqoriroq tarif (Premium Ultra) bor — pastroq tarif sotib olinmaydi"))
        self.assertFalse(bot.check_premium_purchase_eligibility(ultra, "buy_pro_7")[0])
        self.assertEqual(bot.check_premium_purchase_eligibility(state("unlimited", "ultra"), "buy_ultra_30")[0], False)
        self.assertTrue(bot.check_premium_purchase_eligibility(state("expired", "ultra"), "buy_pro_7")[0])

    def test_discount_follows_internal_plus_rules(self):
        """SUPER PRIZ chegirmasi (ichki plus): faol plus (ko'rinadigan Pro) — uzaytirish, ultra — taqiq."""
        action = "buy_plus_30_discount"
        self.assertEqual(bot.check_premium_purchase_eligibility(state("active", "plus"), action), (True, None))
        self.assertEqual(bot.check_premium_purchase_eligibility(state("active", "pro"), action), (True, None))
        self.assertEqual(bot.check_premium_purchase_eligibility(state("free"), action), (True, None))
        ok, reason = bot.check_premium_purchase_eligibility(state("active", "ultra"), action)
        self.assertFalse(ok)
        self.assertIn("Premium Ultra", reason)
        self.assertFalse(bot.check_premium_purchase_eligibility(state("unlimited", "plus"), action)[0])

    def test_unknown_state_is_treated_as_free(self):
        self.assertEqual(bot.check_premium_purchase_eligibility(None, "buy_pro_7"), (True, None))
        self.assertEqual(bot.check_premium_purchase_eligibility({}, "buy_ultra_30"), (True, None))

    def test_purchasable_plans_list(self):
        """"Uzaytirish" tugmalari: joriy tarif (uzaytirish) va undan yuqorilari."""
        cases = {
            ("free", None): [("pro", False), ("plus", False), ("ultra", False)],
            ("expired", "ultra"): [("pro", False), ("plus", False), ("ultra", False)],
            ("active", "pro"): [("pro", True), ("plus", False), ("ultra", False)],
            ("active", "plus"): [("plus", True), ("ultra", False)],
            ("active", "ultra"): [("ultra", True)],
            ("unlimited", "ultra"): [],
            ("unlimited", "pro"): [],
        }
        for (kind, tier), plans in cases.items():
            with self.subTest(state=f"{kind}:{tier}"):
                self.assertEqual(bot.purchasable_premium_plans(state(kind, tier)), plans)

    def test_button_texts(self):
        with mock.patch.dict(os.environ, ENV):
            self.assertEqual(bot.premium_buy_button_text("ultra", True), "🔄 Premium Ultra — yana 30 kun (300 ⭐)")
            self.assertEqual(bot.premium_buy_button_text("pro", True), "🔄 Premium Plus — yana 7 kun (50 ⭐)")
            self.assertEqual(bot.premium_buy_button_text("plus", True), "🔄 Premium Pro — yana 30 kun (150 ⭐)")
            self.assertEqual(bot.premium_buy_button_text("plus", False), "💎 150 Stars → 30 kun Premium Pro")
            self.assertEqual(bot.premium_discount_button_text(True), "🔄 Pro — yana 30 kun — 75⭐ (−50%)")
            self.assertEqual(bot.premium_discount_button_text(False), "💎 Pro — 75⭐ (−50%)")


# ───────────────────── bot tugmasi, /api/invoice va pre_checkout BIR XIL natija ─────────────────────
class EntryPointsAgreeTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        patcher = mock.patch.dict(os.environ, ENV)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.discount = False
        self.view = state("free")

    def patches(self):
        return (mock.patch.object(database, "get_premium_view", side_effect=lambda uid: self.view),
                mock.patch.object(database, "has_discount", side_effect=lambda uid: self.discount),
                mock.patch.object(database, "is_user_banned", return_value=(False, None)),
                not_banned_patch())

    async def via_button(self, action):
        cb = mock.MagicMock()
        cb.data = action
        cb.from_user = SimpleNamespace(id=USER_ID)
        cb.answer = mock.AsyncMock()
        cb.message.answer_invoice = mock.AsyncMock()
        p1, p2, p3, p4 = self.patches()
        with p1, p2, p3, p4:
            await bot.process_pay_stars_tariff(cb)
        if cb.message.answer_invoice.await_count:
            return True, None, cb.message.answer_invoice.await_args.kwargs
        return False, cb.answer.await_args.args[0], None

    async def via_api(self, plan):
        create = mock.AsyncMock(return_value=LINK)
        p1, p2, p3, p4 = self.patches()
        with p1, p2, p3, p4, mock.patch.object(bot, "bot", SimpleNamespace(create_invoice_link=create)):
            result = await bot._api_invoice_action(USER_ID, {"plan": plan})
        if result["ok"]:
            return True, None, create.await_args.kwargs
        self.assertEqual(result["error"], "not_eligible")
        return False, result["message"], None

    async def via_pre_checkout(self, payload, stars):
        q = mock.MagicMock()
        q.from_user = SimpleNamespace(id=USER_ID)
        q.invoice_payload = payload
        q.currency = "XTR"
        q.total_amount = stars
        q.answer = mock.AsyncMock()
        p1, p2, p3, p4 = self.patches()
        with p1, p2, p3, p4:
            await bot.process_pre_checkout(q)
        kwargs = q.answer.await_args.kwargs
        return kwargs["ok"], kwargs.get("error_message")

    async def test_all_entry_points_agree_for_every_state_and_plan(self):
        for kind, tier in STATES:
            self.view = state(kind, tier)
            for buying, (action, payload, stars) in PLANS.items():
                with self.subTest(state=f"{kind}:{tier}", buying=buying):
                    allowed, _ext = expected(kind, tier, buying)
                    btn_ok, btn_msg, btn_invoice = await self.via_button(action)
                    api_ok, api_msg, api_invoice = await self.via_api(action)
                    pre_ok, pre_msg = await self.via_pre_checkout(payload, stars)
                    self.assertEqual((btn_ok, api_ok, pre_ok), (allowed, allowed, allowed))
                    if allowed:
                        for kw in (btn_invoice, api_invoice):
                            self.assertEqual((kw["payload"], kw["prices"][0].amount), (payload, stars))
                    else:
                        want = refusal(kind, tier)
                        self.assertIn(want, btn_msg)
                        self.assertEqual(api_msg, want)                        # API: oddiy matn, ortiqcha belgisiz
                        self.assertEqual(pre_msg, want)

    async def test_discount_agrees_for_active_plus_and_ultra(self):
        self.discount = True
        discount_price = 75
        for kind, tier, allowed in (("active", "plus", True), ("active", "pro", True), ("free", None, True),
                                    ("active", "ultra", False), ("unlimited", "plus", False)):
            self.view = state(kind, tier)
            with self.subTest(state=f"{kind}:{tier}"):
                btn_ok, btn_msg, btn_invoice = await self.via_button("buy_plus_30_discount")
                api_ok, api_msg, api_invoice = await self.via_api("buy_plus_30")      # API'da chegirma serverda avtomatik
                pre_ok, pre_msg = await self.via_pre_checkout(bot.DISCOUNT_PAYLOAD, discount_price)
                self.assertEqual((btn_ok, api_ok, pre_ok), (allowed, allowed, allowed))
                if allowed:
                    for kw in (btn_invoice, api_invoice):
                        self.assertEqual((kw["payload"], kw["prices"][0].amount), (bot.DISCOUNT_PAYLOAD, discount_price))
                else:
                    self.assertEqual(api_msg, pre_msg)

    async def test_pre_checkout_checks_eligibility_after_the_payload_and_amount_checks(self):
        """To'lov summasi / payload tekshiruvi o'zgarmagan: noto'g'ri summa baribir rad etiladi."""
        self.view = state("free")
        ok, _msg = await self.via_pre_checkout("PLUS_30_DAYS", 149)
        self.assertFalse(ok)
        ok, _msg = await self.via_pre_checkout("PLUS_30_DAYS", 150)
        self.assertTrue(ok)

    async def test_pre_checkout_rejects_downgrade_that_was_invoiced_before_upgrade(self):
        """Foydalanuvchi eski invoice'ni (pro) ochiq qoldirib Ultra olgan bo'lsa — pastroq tarif to'lovi to'xtatiladi."""
        self.view = state("active", "ultra")
        ok, msg = await self.via_pre_checkout("PRO_7_DAYS", 50)
        self.assertFalse(ok)
        self.assertIn("Premium Ultra", msg)

    async def test_legacy_payload_follows_the_same_rule(self):
        self.view = state("active", "plus")
        ok, _msg = await self.via_pre_checkout("stars_premium_1month", 50)         # eski payload = ichki pro
        self.assertFalse(ok)
        self.view = state("active", "pro")
        ok, _msg = await self.via_pre_checkout("stars_premium_1month", 50)
        self.assertTrue(ok)


# ───────────────────── muddat qo'shilishi: HAQIQIY SQL (sqlite adapteri) ─────────────────────
class StackingTest(unittest.TestCase):
    def setUp(self):
        self.db = SqliteDB()
        self.addCleanup(self.db.close)
        con = sqlite3.connect(self.db.path)
        con.execute("""CREATE TABLE payment_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, charge_id TEXT UNIQUE, user_id INTEGER, product_id TEXT,
            stars_amount INTEGER, premium_type TEXT, duration_days INTEGER)""")
        con.commit()
        con.close()
        patcher = mock.patch.object(database, "get_uz_now", return_value=NOW)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.n = 0

    def pay(self, tier, charge=None):
        self.n += 1
        _action, payload, stars = PLANS[tier]
        days = {"pro": 7, "plus": 30, "ultra": 30}[tier]
        with self.db.patched():
            return database.process_paid_premium(charge or f"charge_{self.n}", USER_ID, payload, stars, tier, days)

    def user(self, tier, until):
        self.db.add_user(USER_ID, is_premium=1, premium_type=tier, premium_expires_at=until.isoformat(),
                         premium_until=until.isoformat())

    def row(self):
        return self.db.row(USER_ID)

    def expires(self):
        return database._to_uz_datetime(self.row()["premium_expires_at"])

    def test_same_tier_extends_the_expiry_not_replaces_it(self):
        for tier, days in (("pro", 7), ("plus", 30), ("ultra", 30)):
            with self.subTest(tier=tier):
                until = NOW + dt.timedelta(days=10)
                db_user = USER_ID + RANK[tier]
                self.db.add_user(db_user, is_premium=1, premium_type=tier, premium_expires_at=until.isoformat())
                with self.db.patched():
                    granted, new_until = database.process_paid_premium(
                        f"c_{tier}", db_user, PLANS[tier][1], PLANS[tier][2], tier, days)
                self.assertTrue(granted)
                self.assertEqual(new_until, until + dt.timedelta(days=days))        # eski tugash sanasi + tarif muddati
                row = self.db.row(db_user)
                self.assertEqual(row["premium_type"], tier)
                self.assertEqual(database._to_uz_datetime(row["premium_expires_at"]), until + dt.timedelta(days=days))

    def test_ultra_twice_dec_12_to_jan_11_to_feb_10(self):
        """Misol: Ultra 12-dekabrgacha -> yana Ultra -> 11-yanvargacha -> yana -> 10-fevralgacha."""
        self.user("ultra", dt.datetime(2026, 12, 12, 12, 0, tzinfo=UZ))
        granted, until = self.pay("ultra")
        self.assertTrue(granted)
        self.assertEqual(until.strftime("%d.%m.%Y"), "11.01.2027")
        granted, until = self.pay("ultra")
        self.assertEqual(until.strftime("%d.%m.%Y"), "10.02.2027")
        self.assertEqual(self.expires().strftime("%d.%m.%Y"), "10.02.2027")
        self.assertEqual(self.row()["premium_type"], "ultra")
        with self.db.patched():
            view = database.get_premium_view(USER_ID)
        self.assertEqual((view["active"], view["tier"], view["unlimited"]), (True, "ultra", False))

    def test_upgrade_keeps_remaining_days_and_switches_tier(self):
        until = NOW + dt.timedelta(days=3)
        self.user("pro", until)
        granted, new_until = self.pay("ultra")
        self.assertTrue(granted)
        self.assertEqual(new_until, until + dt.timedelta(days=30))
        self.assertEqual(self.row()["premium_type"], "ultra")

    def test_expired_premium_starts_from_now(self):
        self.user("ultra", NOW - dt.timedelta(days=2))
        granted, until = self.pay("pro")
        self.assertEqual(until, NOW + dt.timedelta(days=7))
        self.assertEqual(self.row()["premium_type"], "pro")

    def test_free_user_gets_the_tariff_duration_from_now(self):
        for tier, days in (("pro", 7), ("plus", 30), ("ultra", 30)):
            self.db.add_user(USER_ID + 10 + RANK[tier])
            self.n += 1
            with self.db.patched():
                _ok, until = database.process_paid_premium(
                    f"free_{tier}", USER_ID + 10 + RANK[tier], PLANS[tier][1], PLANS[tier][2], tier, days)
            self.assertEqual(until, NOW + dt.timedelta(days=days), tier)

    def test_repeated_charge_id_does_not_extend_twice(self):
        until = NOW + dt.timedelta(days=10)
        self.user("ultra", until)
        self.assertTrue(self.pay("ultra", charge="dup_1")[0])
        expiry = self.expires()
        self.assertEqual(self.pay("ultra", charge="dup_1"), (False, None))           # takroriy to'lov himoyasi
        self.assertEqual(self.expires(), expiry)

    def test_lower_tier_payment_never_lowers_the_tier(self):
        """DB qatlami himoyasi (xarid qoidasi bunga yo'l qo'ymaydi, lekin zaxira): Ultra + pro to'lov -> Ultra qoladi."""
        until = NOW + dt.timedelta(days=10)
        self.user("ultra", until)
        self.pay("pro")
        self.assertEqual(self.row()["premium_type"], "ultra")

    def test_discount_is_consumed_in_the_same_transaction_for_an_extension(self):
        until = NOW + dt.timedelta(days=5)
        self.db.add_user(USER_ID, is_premium=1, premium_type="plus", premium_expires_at=until.isoformat(), has_discount=1)
        with self.db.patched():
            granted, new_until = database.process_paid_premium(
                "disc_1", USER_ID, bot.DISCOUNT_PAYLOAD, 75, "plus", 30, True)
        self.assertTrue(granted)
        self.assertEqual(new_until, until + dt.timedelta(days=30))
        self.assertEqual(self.row()["has_discount"], 0)
        self.assertEqual(self.row()["premium_type"], "plus")


if __name__ == "__main__":
    unittest.main()
