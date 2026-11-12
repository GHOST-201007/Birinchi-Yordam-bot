"""
test_points_redeem.py — "100 ball -> Premium Plus": matnlar (muddat yo'q), YAGONA mantiq (bot tugmasi va
POST /api/points/redeem) va endpoint.

Mantiq HAQIQIY SQL bilan (tests/sqlite_db.py): ballarni yechish va Premium berish bir tranzaksiyada, muddatsiz Premium
rad etiladi, parallel so'rovlar bitta beradi. Telegram va haqiqiy baza ishlatilmaydi.
"""
import asyncio
import datetime as dt
import os
import re
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest import mock

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("BOT_TOKEN", "123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567890")
os.environ.setdefault("GEMINI_API_KEY", "test_gemini_key")

import bot  # noqa: E402
import database  # noqa: E402
from tests.sqlite_db import SqliteDB  # noqa: E402
from tests.test_miniapp_api import ApiTestBase, USER_ID as API_USER, OTHER_ID, fresh_init_data, premium_view  # noqa: E402

UID = 900000977
ENV = {"PRO_TRIAL_STARS": "50", "PRO_MONTHLY_STARS": "150", "ULTRA_MONTHLY_STARS": "300"}


def read(*parts):
    with open(os.path.join(PROJECT_DIR, *parts), encoding="utf-8") as f:
        return f.read()


def has_word_kun(text):
    """"kun" so'zi (kun, kunlik, kuni, kunga...) bormi."""
    return re.search(r"\bkun", text, re.IGNORECASE) is not None


# ───────────────────────── 1. matnlar: takliflarda MUDDAT yo'q ─────────────────────────
class OfferTextsTest(unittest.IsolatedAsyncioTestCase):
    def test_offer_text_has_no_duration_and_uses_visible_name(self):
        self.assertEqual(bot.redeem_offer_text(), "100 ball → Premium Plus")           # TIER_DISPLAY['pro']
        self.assertEqual(bot.REDEEM_POINTS_COST, 100)
        self.assertFalse(has_word_kun(bot.redeem_offer_text()))

    async def sales_page(self, score, view=None):
        target = mock.MagicMock()
        target.from_user = SimpleNamespace(id=UID)
        target.answer = mock.AsyncMock()
        with mock.patch.dict(os.environ, ENV), \
                mock.patch.object(database, "get_score", return_value=score), \
                mock.patch.object(database, "has_discount", return_value=False), \
                mock.patch.object(bot, "get_web_app_url", mock.AsyncMock(return_value="https://x/app")):
            await bot._show_premium_sales(target, view or database.admin_premium_view(0, None, None))
        args, kwargs = target.answer.await_args
        buttons = [(b.text, b.callback_data) for row in kwargs["reply_markup"].inline_keyboard for b in row]
        return args[0], buttons

    async def test_sales_page_line_and_buttons_have_no_duration(self):
        text, buttons = await self.sales_page(13)
        self.assertIn("• <b>100 ball → Premium Plus</b>", text)
        self.assertIn(("🎁 100 ball → Premium Plus (Yana 87 ball kerak)", "redeem_points_info"), buttons)
        text, buttons = await self.sales_page(100)
        self.assertIn(("🎁 100 ball → Premium Plus", "redeem_points_premium"), buttons)
        for label, callback in buttons:
            if callback and callback.startswith("redeem_points"):
                self.assertFalse(has_word_kun(label), label)
        reward = text[text.index("BEPUL REWARD"): text.index("Botda to'plagan")]
        self.assertFalse(has_word_kun(reward), reward)

    async def test_info_alert_has_no_duration(self):
        cb = mock.MagicMock()
        cb.from_user = SimpleNamespace(id=UID)
        cb.answer = mock.AsyncMock()
        with mock.patch.object(database, "get_score", return_value=13):
            await bot.process_redeem_points_info(cb)
        text = cb.answer.await_args.args[0]
        self.assertEqual(text, "⚠️ Sizda 13 ball bor. Premium Plus uchun yana 87 ball to'plashingiz kerak!")
        self.assertFalse(has_word_kun(text))

    def test_success_message_shows_the_expiry_date(self):
        now = dt.datetime(2026, 11, 12, 12, 0, tzinfo=dt.timezone(dt.timedelta(hours=5)))
        pro = database.admin_premium_view(1, "pro", (now + dt.timedelta(days=3)).isoformat(), now)
        self.assertEqual(bot.redeem_success_message(pro),
                         "100 ball yechildi! Premium Plus faollashdi — tugash: 15.11.2026")
        ultra = database.admin_premium_view(1, "ultra", (now + dt.timedelta(days=20)).isoformat(), now)
        self.assertEqual(bot.redeem_success_message(ultra),
                         "100 ball yechildi! Premium Ultra muddati uzaytirildi — tugash: 02.12.2026")
        self.assertEqual(bot.redeem_success_message(None), "100 ball yechildi! Premium Plus faollashdi")

    def test_no_100_ball_offer_in_the_sources_mentions_a_duration(self):
        """bot.py, Mini App va xizmatlardagi "100 ball" qatorlarida "kun" so'zi yo'q (boshqa "kun" yozuvlariga tegilmagan)."""
        files = [("bot.py",), ("app", "app.js"), ("app", "index.html")]
        services = os.path.join(PROJECT_DIR, "services")
        files += [("services", name) for name in os.listdir(services) if name.endswith(".py")]
        checked = 0
        for parts in files:
            for number, line in enumerate(read(*parts).splitlines(), 1):
                if re.search(r"100 ?ball|REDEEM_COST|REDEEM_POINTS_COST", line, re.IGNORECASE):
                    checked += 1
                    # Ichki hujjat izohlari (#, //) tekshirilmaydi: foydalanuvchi ko'rmaydi
                    code = re.sub(r"\s(#|//)\s.*$", "", line)
                    self.assertFalse(has_word_kun(code), f"{'/'.join(parts)}:{number}: {line.strip()}")
        self.assertGreater(checked, 5)

    def test_other_day_texts_are_untouched(self):
        """Faqat 100 ball takliflari o'zgardi: baraban 1 kunlik sovrini va kunlik bonus matnlari joyida."""
        src = read("bot.py")
        self.assertIn("1 kunlik Premium {TIER_DISPLAY['pro']} yutishingiz mumkin", src)
        self.assertIn("Kunlik bonus:", src)


# ───────────────────────── 2. YAGONA mantiq (haqiqiy SQL) ─────────────────────────
class SharedLogicBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = SqliteDB()
        self.addCleanup(self.db.close)
        for target, value in (("get_connection", self.db.connect),
                              ("is_user_banned", mock.MagicMock(return_value=(False, None)))):
            patcher = mock.patch.object(database, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.sync = mock.MagicMock()
        patcher = mock.patch.object(bot, "schedule_personal_menu_sync", self.sync)
        patcher.start()
        self.addCleanup(patcher.stop)
        bot._premium_menu_cache.clear()
        self.addCleanup(bot._premium_menu_cache.clear)
        bot._redeem_in_flight.clear()

    def user(self, score, **cols):
        self.db.add_user(UID, medicine_score=score, **cols)

    def row(self):
        return self.db.row(UID)

    def expires(self):
        return database._to_uz_datetime(self.row()["premium_expires_at"])

    async def redeem(self):
        return await bot.redeem_points_for_premium(UID, SimpleNamespace())


class RedeemLogicTest(SharedLogicBase):
    async def test_enough_points_deduct_100_and_grant_3_days_of_pro(self):
        self.user(130)
        result = await self.redeem()
        self.assertEqual((result["ok"], result["reason"], result["score"]), (True, None, 30))
        row = self.row()
        self.assertEqual((row["medicine_score"], row["is_premium"], row["premium_type"]), (30, 1, "pro"))
        self.assertAlmostEqual((self.expires() - database.get_uz_now()).total_seconds(), 3 * 86400, delta=120)
        self.assertRegex(result["message"], r"^100 ball yechildi! Premium Plus faollashdi — tugash: \d\d\.\d\d\.\d{4}$")
        self.assertEqual((result["view"]["active"], result["view"]["tier"]), (True, "pro"))
        self.sync.assert_called_once()                                             # shaxsiy "👑 Ilova" tugmasi
        self.assertEqual(self.sync.call_args.args[1:], (UID, True))
        self.assertEqual(bot.cached_premium_view(UID), {"active": True, "tier": "pro"})   # menyu keshi

    async def test_exactly_100_points_is_enough(self):
        self.user(100)
        result = await self.redeem()
        self.assertTrue(result["ok"])
        self.assertEqual(self.row()["medicine_score"], 0)

    async def test_not_enough_points_changes_nothing(self):
        self.user(87)
        result = await self.redeem()
        self.assertEqual((result["ok"], result["reason"], result["score"]), (False, "not_enough", 87))
        self.assertEqual(result["message"], "Ballaringiz yetarli emas (hozirda 87 ball bor).")
        row = self.row()
        self.assertEqual((row["medicine_score"], row["is_premium"]), (87, 0))
        self.sync.assert_not_called()

    async def test_unlimited_premium_is_refused_and_points_stay(self):
        self.user(150, is_premium=1, premium_type="ultra", premium_expires_at=None)
        result = await self.redeem()
        self.assertEqual((result["ok"], result["reason"], result["score"]), (False, "unlimited", 150))
        self.assertIn("muddatsiz Premium", result["message"])
        row = self.row()
        self.assertEqual((row["medicine_score"], row["premium_type"], row["premium_expires_at"]), (150, "ultra", None))
        self.sync.assert_not_called()

    async def test_database_layer_also_protects_unlimited_premium(self):
        """Holat o'qilmay qolsa yoki poyga bo'lsa ham: check_and_grant_premium muddatsizni buzmaydi va ball yechmaydi
        (kunlik bonus / referal / baraban avto-berishi ham shu funksiyadan o'tadi)."""
        self.user(150, is_premium=1, premium_type="plus", premium_expires_at=None)
        self.assertFalse(database.check_and_grant_premium(UID))
        row = self.row()
        self.assertEqual((row["medicine_score"], row["premium_type"], row["premium_expires_at"]), (150, "plus", None))

    async def test_banned_user_is_refused(self):
        self.user(150)
        with mock.patch.object(database, "is_user_banned", return_value=(True, "ban")):
            result = await self.redeem()
        self.assertEqual((result["ok"], result["reason"]), (False, "banned"))
        self.assertEqual(self.row()["medicine_score"], 150)
        self.sync.assert_not_called()

    async def test_active_premium_stacks_and_higher_tier_is_kept(self):
        until = database.get_uz_now() + dt.timedelta(days=10)
        self.user(100, is_premium=1, premium_type="ultra", premium_expires_at=until.isoformat())
        result = await self.redeem()
        self.assertTrue(result["ok"])
        self.assertEqual(self.row()["premium_type"], "ultra")
        self.assertAlmostEqual((self.expires() - until).total_seconds(), 3 * 86400, delta=5)
        self.assertIn("Premium Ultra muddati uzaytirildi — tugash:", result["message"])

    async def test_expired_flag_counts_as_free(self):
        past = database.get_uz_now() - dt.timedelta(days=2)
        self.user(100, is_premium=1, premium_type="ultra", premium_expires_at=past.isoformat())
        result = await self.redeem()
        self.assertTrue(result["ok"])
        self.assertEqual(self.row()["premium_type"], "pro")

    async def test_double_click_with_exactly_100_points_grants_once(self):
        self.user(100)
        results = await asyncio.gather(self.redeem(), self.redeem())
        self.assertEqual(sorted(r["ok"] for r in results), [False, True])
        self.assertEqual(self.row()["medicine_score"], 0)
        self.assertAlmostEqual((self.expires() - database.get_uz_now()).total_seconds(), 3 * 86400, delta=120)  # 6 emas

    async def test_double_click_with_200_points_does_not_spend_twice(self):
        """Parallel so'rovlar ketma-ket emas, BITTA ishlaydi: tasodifiy qo'sh bosish 200 ballni yechmaydi."""
        self.user(200)
        results = await asyncio.gather(self.redeem(), self.redeem(), self.redeem())
        self.assertEqual([r["ok"] for r in results].count(True), 1)
        self.assertEqual(sorted(r["reason"] for r in results if not r["ok"]), ["busy", "busy"])
        self.assertEqual(self.row()["medicine_score"], 100)
        # keyin yana bosish mumkin (in-flight belgisi tozalangan)
        self.assertTrue((await self.redeem())["ok"])
        self.assertEqual(self.row()["medicine_score"], 0)

    def test_database_layer_is_atomic_under_20_parallel_calls(self):
        self.user(100)
        with ThreadPoolExecutor(max_workers=20) as pool:
            results = list(pool.map(lambda _: database.check_and_grant_premium(UID), range(20)))
        self.assertEqual(results.count(True), 1)
        self.assertEqual(self.row()["medicine_score"], 0)
        self.assertAlmostEqual((self.expires() - database.get_uz_now()).total_seconds(), 3 * 86400, delta=120)

    async def test_in_flight_mark_is_released_after_an_error(self):
        self.user(100)
        with mock.patch.object(database, "check_and_grant_premium", side_effect=RuntimeError("baza uzildi")):
            with self.assertRaises(RuntimeError):
                await self.redeem()
        self.assertNotIn(UID, bot._redeem_in_flight)
        self.assertTrue((await self.redeem())["ok"])


# ───────────────── bot tugmasi va API BIR XIL natija ─────────────────
class ButtonAndApiAgreeTest(unittest.IsolatedAsyncioTestCase):
    SCENARIOS = {
        "enough": dict(score=130),
        "not_enough": dict(score=13),
        "unlimited": dict(score=150, is_premium=1, premium_type="ultra", premium_expires_at=None),
        "ultra_active": dict(score=100, is_premium=1, premium_type="ultra",
                             premium_expires_at=(dt.datetime.now(dt.timezone(dt.timedelta(hours=5)))
                                                 + dt.timedelta(days=10)).isoformat()),
    }

    async def run_both(self, name):
        results = {}
        for channel in ("button", "api"):
            db = SqliteDB()
            self.addCleanup(db.close)
            cols = dict(self.SCENARIOS[name])
            db.add_user(UID, medicine_score=cols.pop("score"), **cols)
            with db.patched(), \
                    mock.patch.object(database, "is_user_banned", return_value=(False, None)), \
                    mock.patch.object(database, "get_ai_quota_detail", return_value=(14, 15, 0)), \
                    mock.patch.object(bot, "schedule_personal_menu_sync", mock.MagicMock()), \
                    mock.patch.object(bot, "_show_premium_page", mock.AsyncMock()):
                bot._premium_menu_cache.clear()
                if channel == "api":
                    results[channel] = await bot._api_points_redeem_action(UID)
                else:
                    cb = mock.MagicMock()
                    cb.from_user = SimpleNamespace(id=UID)
                    cb.answer = mock.AsyncMock()
                    cb.message.answer = mock.AsyncMock()
                    cb.bot = SimpleNamespace()
                    await bot.process_redeem_points_premium(cb)
                    results[channel] = cb.answer.await_args.args[0]
            results[channel + "_row"] = db.row(UID)
        return results

    async def test_same_outcome_for_every_scenario(self):
        for name in self.SCENARIOS:
            with self.subTest(scenario=name):
                r = await self.run_both(name)
                api = r["api"]
                prefix = "🎉 " if api["ok"] else "⚠️ "
                self.assertEqual(r["button"], prefix + api["message"])              # bir xil matn
                for key in ("medicine_score", "is_premium", "premium_type"):          # bir xil bazadagi natija
                    self.assertEqual(r["button_row"][key], r["api_row"][key], key)
                self.assertEqual(api["score"], r["api_row"]["medicine_score"])


# ───────────────── POST /api/points/redeem ─────────────────
class RedeemEndpointTest(ApiTestBase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.view_state = premium_view()
        self.m["view"].side_effect = lambda uid: self.view_state
        self.grant_calls = []
        self.grant_results = [True]

        def grant(uid):
            self.grant_calls.append(uid)
            result = self.grant_results.pop(0) if self.grant_results else False
            if result:
                self.view_state = premium_view("pro", days=3)
                self.score["v"] = 30
            return result

        self.grant = mock.MagicMock(side_effect=grant)
        self.sync = mock.MagicMock()
        for patcher in (mock.patch.object(bot.database, "check_and_grant_premium", self.grant),
                        mock.patch.object(bot, "schedule_personal_menu_sync", self.sync)):
            patcher.start()
            self.addCleanup(patcher.stop)
        bot._premium_menu_cache.clear()
        bot._redeem_in_flight.clear()
        self.score["v"] = 130

    async def test_success_returns_new_state(self):
        resp, data = await self.post("/api/points/redeem")
        self.assertEqual(resp.status, 200)
        self.assertTrue(data["ok"])
        self.assertIsNone(data["reason"])
        self.assertRegex(data["message"], r"^100 ball yechildi! Premium Plus faollashdi — tugash: \d\d\.\d\d\.\d{4}$")
        self.assertEqual((data["score"], data["cost"]), (30, 100))
        # Yangi holat: _premium_quota_fields (header, karta va AI hisoblagichi uchun)
        self.assertEqual((data["is_premium"], data["premium_type"], data["premium_unlimited"]), (True, "pro", False))
        self.assertTrue(data["premium_expires_at"])
        self.assertEqual(data["premium_days_left"], 3)
        for key in ("ai_remaining", "ai_limit", "ai_bonus"):
            self.assertIn(key, data)
        self.assertEqual(self.grant_calls, [API_USER])
        # menyu keshi va shaxsiy tugma
        self.sync.assert_called_once_with(bot.bot, API_USER, True)
        self.assertEqual(bot.cached_premium_view(API_USER), {"active": True, "tier": "pro"})

    async def test_not_enough_points(self):
        self.grant_results = [False]
        self.score["v"] = 13
        resp, data = await self.post("/api/points/redeem")
        self.assertEqual(resp.status, 200)
        self.assertEqual((data["ok"], data["reason"], data["score"]), (False, "not_enough", 13))
        self.assertEqual(data["message"], "Ballaringiz yetarli emas (hozirda 13 ball bor).")
        self.assertFalse(data["is_premium"])
        self.sync.assert_not_called()

    async def test_unlimited_premium_is_refused_without_touching_points(self):
        self.view_state = premium_view("ultra", unlimited=True)
        resp, data = await self.post("/api/points/redeem")
        self.assertEqual((resp.status, data["ok"], data["reason"]), (200, False, "unlimited"))
        self.assertIn("muddatsiz Premium", data["message"])
        self.assertTrue(data["premium_unlimited"])
        self.assertEqual(self.grant_calls, [])
        self.sync.assert_not_called()

    async def test_banned_user_403_and_nothing_is_spent(self):
        self.m["banned"].return_value = (True, "ban")
        resp, data = await self.post("/api/points/redeem")
        self.assertEqual((resp.status, data), (403, {"ok": False, "error": "banned"}))
        self.assertEqual(self.grant_calls, [])

    async def test_forged_init_data_403_and_no_db_calls(self):
        good = fresh_init_data()
        bad = good[:-1] + ("0" if good[-1] != "0" else "1")
        resp, data = await self.post("/api/points/redeem", init_data=bad)
        self.assertEqual((resp.status, data), (403, {"ok": False, "error": "forbidden"}))
        self.assertEqual(self.grant_calls, [])
        self.m["banned"].assert_not_called()
        self.m["score"].assert_not_called()
        self.m["view"].assert_not_called()

    async def test_missing_or_malformed_body_is_rejected(self):
        resp, data = await self.post("/api/points/redeem", raw="{}")
        self.assertEqual((resp.status, data), (400, {"ok": False, "error": "bad_request"}))
        resp, _ = await self.post("/api/points/redeem", raw='{"init_data":"x"}', content_type="text/plain")
        self.assertEqual(resp.status, 415)
        self.assertEqual(self.grant_calls, [])

    async def test_only_post_is_allowed(self):
        for method in ("get", "put", "delete"):
            resp = await getattr(self.client, method)("/api/points/redeem")
            self.assertEqual(resp.status, 405)

    async def test_client_supplied_fields_are_ignored(self):
        extra = {"user_id": OTHER_ID, "cost": 1, "score": 9999, "points": 9999, "tier": "ultra", "days": 365}
        resp, data = await self.post("/api/points/redeem", extra=extra)
        self.assertEqual(self.grant_calls, [API_USER])                               # faqat initData'dagi foydalanuvchi
        self.assertEqual((data["cost"], data["score"], data["premium_type"]), (100, 30, "pro"))

    async def test_two_parallel_requests_grant_once(self):
        self.score["v"] = 100
        self.grant_results = [True, False, False]
        first, second = await asyncio.gather(self.post("/api/points/redeem"), self.post("/api/points/redeem"))
        outcomes = sorted(d["ok"] for _r, d in (first, second))
        self.assertEqual(outcomes, [False, True])
        self.assertEqual(self.sync.call_count, 1)

    async def test_rate_limit_is_shared_with_other_endpoints(self):
        for _ in range(20):
            await self.post("/api/state")
        resp, data = await self.post("/api/points/redeem")
        self.assertEqual((resp.status, data), (429, {"ok": False, "error": "rate_limited"}))

    async def test_state_already_has_the_user_score(self):
        resp, data = await self.post("/api/state")
        self.assertIsInstance(data["score"], int)

    async def test_route_is_registered_with_api_prefix(self):
        paths = {r.canonical for r in self.client.app.router.resources()}
        self.assertIn("/api/points/redeem", paths)
        self.assertNotIn("/points/redeem", paths)


if __name__ == "__main__":
    unittest.main()
