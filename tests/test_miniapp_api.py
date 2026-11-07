"""
test_miniapp_api.py — Mini App /api/state, /api/spin/claim, /api/bonus/claim.

aiohttp serveri xotirada (TestServer) ishga tushiriladi; DB funksiyalari mock qilinadi.
Haqiqiy Telegram, Gemini yoki bazaga murojaat qilinmaydi.
"""
import contextlib
import json
import os
import sys
import time
import unittest
from datetime import timedelta
from unittest import mock

from aiohttp.test_utils import TestClient, TestServer

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("BOT_TOKEN", "123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567890")
os.environ.setdefault("GEMINI_API_KEY", "test_gemini_key")

import bot  # noqa: E402
from tests.test_init_data import TOKEN as TEST_TOKEN, make as make_init_data  # noqa: E402

USER_ID = 424242            # test_init_data.USER["id"]
OTHER_ID = 999999
SPIN_OK_MSG = "Tabriklaymiz! Siz Omad barabanidan <b>+5 ball</b> yutib oldingiz! \U0001F389"
SPIN_USED_MSG = "Sizda tasdiqlanmagan yutuq topilmadi yoki u allaqachon hisobingizga qo'shilgan!"


def fresh_init_data(**kw):
    return make_init_data(auth_date=int(time.time()), **kw)


class ApiTestBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        db = bot.database
        self.score = {"v": 2}
        self.m = {
            "banned": mock.MagicMock(return_value=(False, "")),
            "score": mock.MagicMock(side_effect=lambda uid: self.score["v"]),
            "bonus_info": mock.MagicMock(return_value={"streak": 3, "is_claimed_today": False}),
            "prize": mock.MagicMock(return_value=5),
            "spin": mock.MagicMock(return_value=(True, SPIN_OK_MSG)),
            "daily": mock.MagicMock(return_value=(True, 3, 3)),
            "spin_state": mock.MagicMock(return_value=(None, 5)),
        }
        stack.enter_context(mock.patch.object(bot, "TOKEN", TEST_TOKEN))
        stack.enter_context(mock.patch.object(bot, "api_rate_limiter", bot.ApiRateLimiter()))
        stack.enter_context(mock.patch.object(db, "is_user_banned", self.m["banned"]))
        stack.enter_context(mock.patch.object(db, "get_score", self.m["score"]))
        stack.enter_context(mock.patch.object(db, "get_daily_bonus_info", self.m["bonus_info"]))
        stack.enter_context(mock.patch.object(db, "generate_or_get_spin_prize", self.m["prize"]))
        stack.enter_context(mock.patch.object(db, "check_and_grant_spin_bonus", self.m["spin"]))
        stack.enter_context(mock.patch.object(db, "check_and_grant_daily_bonus", self.m["daily"]))
        stack.enter_context(mock.patch.object(bot, "_read_spin_state", self.m["spin_state"]))

        self.client = TestClient(TestServer(bot.create_web_app()))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)

    async def post(self, path, init_data=None, extra=None, raw=None, content_type="application/json"):
        if raw is None:
            body = {"init_data": fresh_init_data() if init_data is None else init_data}
            body.update(extra or {})
            raw = json.dumps(body)
        resp = await self.client.post(path, data=raw, headers={"Content-Type": content_type})
        try:
            data = await resp.json(content_type=None)
        except Exception:
            data = None
        return resp, data

    def assert_no_db_calls(self):
        for name, m in self.m.items():
            m.assert_not_called()


class AuthTest(ApiTestBase):
    PATHS = ("/api/state", "/api/spin/claim", "/api/bonus/claim")

    async def test_broken_hash_403_and_no_db_calls(self):
        good = fresh_init_data()
        bad = good[:-1] + ("0" if good[-1] != "0" else "1")
        for path in self.PATHS:
            with self.subTest(path=path):
                resp, data = await self.post(path, init_data=bad)
                self.assertEqual(resp.status, 403)
                self.assertEqual(data, {"ok": False, "error": "forbidden"})
        self.assert_no_db_calls()

    async def test_auth_date_25_hours_old_403(self):
        old = make_init_data(auth_date=int(time.time()) - 25 * 3600)
        for path in self.PATHS:
            resp, _ = await self.post(path, init_data=old)
            self.assertEqual(resp.status, 403, path)
        self.assert_no_db_calls()

    async def test_auth_date_future_5_minutes_403(self):
        future = make_init_data(auth_date=int(time.time()) + 300)
        for path in self.PATHS:
            resp, _ = await self.post(path, init_data=future)
            self.assertEqual(resp.status, 403, path)
        self.assert_no_db_calls()

    async def test_body_user_id_is_ignored(self):
        extra = {"user_id": OTHER_ID, "userId": OTHER_ID, "id": OTHER_ID, "user": {"id": OTHER_ID},
                 "points": 1000, "prize": 10}
        for path in self.PATHS:
            resp, data = await self.post(path, extra=extra)
            self.assertEqual(resp.status, 200, path)
        # Hamma DB chaqiruvlari faqat initData ichidagi id bilan
        for name in ("banned", "score", "bonus_info", "prize", "daily"):
            for call in self.m[name].call_args_list:
                self.assertEqual(call.args[0], USER_ID, name)
        # Klient yuborgan ball e'tiborga olinmaydi: server doim 0 uzatadi
        self.m["spin"].assert_called_once_with(USER_ID, 0)
        self.m["spin_state"].assert_any_call(USER_ID)
        self.assertNotIn(OTHER_ID, [c.args[0] for m in self.m.values() for c in m.call_args_list])

    async def test_banned_user_403_and_no_claim(self):
        self.m["banned"].return_value = (True, "ban")
        for path in self.PATHS:
            resp, data = await self.post(path)
            self.assertEqual(resp.status, 403, path)
            self.assertEqual(data, {"ok": False, "error": "banned"})
        self.m["spin"].assert_not_called()
        self.m["daily"].assert_not_called()


class RequestShapeTest(ApiTestBase):
    async def test_only_post_allowed(self):
        for path in ("/api/state", "/api/spin/claim", "/api/bonus/claim"):
            for method in ("get", "put", "delete"):
                resp = await getattr(self.client, method)(path)
                self.assertEqual(resp.status, 405, f"{method} {path}")
        self.assert_no_db_calls()

    async def test_routes_registered_with_api_prefix(self):
        paths = {r.canonical for r in self.client.app.router.resources()}
        self.assertTrue({"/api/state", "/api/spin/claim", "/api/bonus/claim"} <= paths)
        self.assertNotIn("/state", paths)
        resp = await self.client.post("/state", data="{}")
        self.assertEqual(resp.status, 404)

    async def test_health_still_works(self):
        resp = await self.client.get("/health")
        self.assertEqual(resp.status, 200)

    async def test_wrong_content_type_415(self):
        resp, _ = await self.post("/api/state", raw=json.dumps({"init_data": fresh_init_data()}),
                                  content_type="text/plain")
        self.assertEqual(resp.status, 415)
        self.assert_no_db_calls()

    async def test_oversized_body_413(self):
        raw = json.dumps({"init_data": fresh_init_data(), "pad": "x" * 5000})
        resp, data = await self.post("/api/state", raw=raw)
        self.assertEqual(resp.status, 413)
        self.assertEqual(data, {"ok": False, "error": "payload_too_large"})
        self.assert_no_db_calls()

    async def test_malformed_bodies_400(self):
        for raw in ("not json", "[]", "123", "{}", '{"init_data": 5}', '{"init_data": null}', ""):
            with self.subTest(raw=raw):
                resp, data = await self.post("/api/state", raw=raw)
                self.assertEqual(resp.status, 400)
                self.assertEqual(data, {"ok": False, "error": "bad_request"})
        self.assert_no_db_calls()

    async def test_responses_not_cacheable(self):
        resp, _ = await self.post("/api/state")
        self.assertEqual(resp.headers.get("Cache-Control"), "no-store")


class RateLimitTest(ApiTestBase):
    async def test_21st_request_is_429(self):
        for i in range(20):
            resp, _ = await self.post("/api/state")
            self.assertEqual(resp.status, 200, f"{i + 1}-so'rov")
        resp, data = await self.post("/api/state")
        self.assertEqual(resp.status, 429)
        self.assertEqual(data, {"ok": False, "error": "rate_limited"})
        self.assertIn("Retry-After", resp.headers)

    async def test_limit_is_per_user_and_shared_across_endpoints(self):
        for _ in range(10):
            await self.post("/api/state")
        for _ in range(10):
            await self.post("/api/bonus/claim")
        resp, _ = await self.post("/api/spin/claim")
        self.assertEqual(resp.status, 429)
        # Boshqa foydalanuvchiga ta'sir qilmaydi
        other = fresh_init_data(user={"id": OTHER_ID, "first_name": "Vali"})
        resp, _ = await self.post("/api/state", init_data=other)
        self.assertEqual(resp.status, 200)

    async def test_rejected_requests_do_not_consume_quota(self):
        for _ in range(30):
            resp, _ = await self.post("/api/state", init_data="garbage")
            self.assertEqual(resp.status, 403)
        resp, _ = await self.post("/api/state")
        self.assertEqual(resp.status, 200)


class StateTest(ApiTestBase):
    async def test_state_fields(self):
        self.score["v"] = 17
        resp, data = await self.post("/api/state")
        self.assertEqual(resp.status, 200)
        self.assertEqual(data, {"ok": True, "score": 17, "streak": 3, "daily_claimed": False,
                                "prize": 5, "cooldown_seconds": 0})

    async def test_super_prize_is_zero_not_null(self):
        self.m["prize"].return_value = 0
        _, data = await self.post("/api/state")
        self.assertEqual(data["prize"], 0)
        self.assertEqual(data["cooldown_seconds"], 0)

    async def test_cooldown_active_prize_null(self):
        one_hour_ago = (bot.database.get_uz_now() - timedelta(hours=1)).isoformat()
        self.m["prize"].return_value = None
        self.m["spin_state"].return_value = (one_hour_ago, None)
        _, data = await self.post("/api/state")
        self.assertIsNone(data["prize"])
        self.assertGreater(data["cooldown_seconds"], 0)
        self.assertAlmostEqual(data["cooldown_seconds"], 23 * 3600, delta=5)

    async def test_daily_claimed_flag(self):
        self.m["bonus_info"].return_value = {"streak": 4, "is_claimed_today": True}
        _, data = await self.post("/api/state")
        self.assertTrue(data["daily_claimed"])
        self.assertEqual(data["streak"], 4)


class SpinClaimTest(ApiTestBase):
    async def test_double_claim_second_is_not_ok_and_score_added_once(self):
        claimed = {"done": False}

        def fake_claim(uid, points):
            if claimed["done"]:
                return False, SPIN_USED_MSG
            claimed["done"] = True
            self.score["v"] += 5
            return True, SPIN_OK_MSG

        self.m["spin"].side_effect = fake_claim
        r1, d1 = await self.post("/api/spin/claim")
        r2, d2 = await self.post("/api/spin/claim")
        self.assertEqual((r1.status, r2.status), (200, 200))
        self.assertTrue(d1["ok"])
        self.assertEqual(d1["score"], 7)
        self.assertFalse(d2["ok"])
        self.assertEqual(d2["score"], 7)          # ikki marta qo'shilmadi
        self.assertEqual(self.score["v"], 7)

    async def test_message_is_plain_text_without_html(self):
        _, data = await self.post("/api/spin/claim")
        self.assertIn("+5 ball", data["message"])
        self.assertNotIn("<", data["message"])
        self.assertNotIn(">", data["message"])

    async def test_is_super_only_when_claim_succeeds_with_super_prize(self):
        self.m["spin_state"].return_value = (None, 0)
        self.m["spin"].return_value = (True, "SUPER PRIZ! <b>50%</b> chegirma")
        _, data = await self.post("/api/spin/claim")
        self.assertTrue(data["ok"])
        self.assertTrue(data["is_super"])

        self.m["spin"].return_value = (False, SPIN_USED_MSG)
        _, data = await self.post("/api/spin/claim")
        self.assertFalse(data["ok"])
        self.assertFalse(data["is_super"])

    async def test_normal_prize_is_not_super(self):
        _, data = await self.post("/api/spin/claim")
        self.assertFalse(data["is_super"])


class BonusClaimTest(ApiTestBase):
    async def test_bonus_granted(self):
        self.score["v"] = 5
        _, data = await self.post("/api/bonus/claim")
        self.assertEqual((data["ok"], data["points"], data["streak"], data["score"]), (True, 3, 3, 5))
        self.assertIn("+3 ball", data["message"])

    async def test_bonus_already_claimed(self):
        self.m["daily"].return_value = (False, 0, 3)
        resp, data = await self.post("/api/bonus/claim")
        self.assertEqual(resp.status, 200)
        self.assertFalse(data["ok"])
        self.assertEqual(data["points"], 0)
        self.assertIn("olib bo'lgansiz", data["message"])


class ErrorHandlingTest(ApiTestBase):
    async def test_db_error_returns_generic_500_without_details(self):
        self.m["score"].side_effect = RuntimeError("psycopg2.OperationalError: password=SECRET-DB-DETAIL host=db.internal")
        with self.assertLogs(level="ERROR"):
            resp, data = await self.post("/api/state")
        self.assertEqual(resp.status, 500)
        self.assertEqual(data, {"ok": False, "error": "server_error"})
        text = json.dumps(data)
        for leak in ("SECRET", "psycopg2", "Traceback", "RuntimeError"):
            self.assertNotIn(leak, text)

    async def test_init_data_never_logged(self):
        marker = "LOG-MARKER-FIRSTNAME"
        init = fresh_init_data(user={"id": USER_ID, "first_name": marker})
        self.m["score"].side_effect = RuntimeError("boom")
        with self.assertLogs(level="DEBUG") as logs:
            await self.post("/api/state", init_data=init)
            await self.post("/api/state", init_data=init[:-3] + "xyz")      # 403 yo'li
        joined = "\n".join(logs.output)
        self.assertIn("API state xatosi", joined)
        self.assertNotIn(marker, joined)
        self.assertNotIn(init, joined)
        self.assertNotIn("hash=", joined)


class BindTest(unittest.IsolatedAsyncioTestCase):
    async def test_web_server_binds_to_localhost_only(self):
        runner = mock.MagicMock()
        runner.setup = mock.AsyncMock()
        site = mock.MagicMock()
        site.start = mock.AsyncMock()
        with mock.patch.object(bot.web, "AppRunner", return_value=runner), \
             mock.patch.object(bot.web, "TCPSite", return_value=site) as tcp_site, \
             mock.patch.dict(os.environ, {"PORT": "19999"}):
            await bot.start_web_server()
        args = tcp_site.call_args.args
        self.assertEqual(args[1], "127.0.0.1")
        self.assertEqual(args[2], 19999)
        self.assertNotEqual(args[1], "0.0.0.0")


class RateLimiterUnitTest(unittest.TestCase):
    def test_window_expires(self):
        rl = bot.ApiRateLimiter(limit=3, window=60)
        self.assertTrue(all(rl.allow(1, now=100.0 + i) for i in range(3)))
        self.assertFalse(rl.allow(1, now=110.0))
        self.assertTrue(rl.allow(1, now=161.0))       # eng eski yozuv oynadan chiqdi

    def test_stale_users_cleaned_up(self):
        rl = bot.ApiRateLimiter(limit=3, window=60)
        rl.CLEANUP_EVERY = 50
        for uid in range(1, 50):
            rl.allow(uid, now=10.0)
        self.assertEqual(len(rl._hits), 49)
        rl.allow(1000, now=500.0)                      # 50-chaqiruv -> tozalash
        self.assertEqual(list(rl._hits), [1000])


class HelpersUnitTest(unittest.TestCase):
    def test_cooldown_iso_naive_and_aware(self):
        now = bot.database.get_uz_now()
        naive = (now - timedelta(hours=2)).replace(tzinfo=None).isoformat()
        aware = (now - timedelta(hours=2)).isoformat()
        for value in (naive, aware):
            self.assertAlmostEqual(bot._spin_cooldown_seconds(value, now), 22 * 3600, delta=1)

    def test_cooldown_elapsed_and_empty(self):
        now = bot.database.get_uz_now()
        self.assertEqual(bot._spin_cooldown_seconds((now - timedelta(hours=25)).isoformat(), now), 0)
        self.assertEqual(bot._spin_cooldown_seconds(None, now), 0)
        self.assertEqual(bot._spin_cooldown_seconds("", now), 0)

    def test_cooldown_legacy_date_format(self):
        now = bot.database.get_uz_now()
        today = now.date().isoformat()
        yesterday = (now - timedelta(days=1)).date().isoformat()
        remaining = bot._spin_cooldown_seconds(today, now)
        self.assertGreater(remaining, 0)
        self.assertLessEqual(remaining, 24 * 3600)
        self.assertEqual(bot._spin_cooldown_seconds(yesterday, now), 0)

    def test_read_spin_state_reads_columns_only(self):
        executed = []

        class Cur:
            def execute(self, sql, params=()):
                executed.append((" ".join(sql.split()), params))

            def fetchone(self):
                return ("2026-11-07T10:00:00+05:00", 3)

        @contextlib.contextmanager
        def fake_managed():
            yield mock.MagicMock(), Cur()

        with mock.patch.object(bot.database, "_managed_cursor", fake_managed):
            self.assertEqual(bot._read_spin_state(USER_ID), ("2026-11-07T10:00:00+05:00", 3))
        self.assertEqual(executed, [("SELECT last_spin_date, pending_spin_prize FROM users WHERE user_id = %s", (USER_ID,))])

    def test_plain_text(self):
        self.assertEqual(bot._plain_text("<b>+5 ball</b> &amp; <i>omad</i>"), "+5 ball & omad")
        self.assertEqual(bot._plain_text(None), "")


if __name__ == "__main__":
    unittest.main()
