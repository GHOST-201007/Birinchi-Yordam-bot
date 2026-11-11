"""
test_webhook.py — polling'dan webhook'ga o'tish (WEBHOOK_BASE_URL + WEBHOOK_SECRET).

Haqiqiy Telegram, Gemini yoki bazaga murojaat qilinmaydi: Dispatcher soxta, aiohttp serveri xotirada (TestServer).
"""
import asyncio
import json
import os
import sys
import types
import unittest
from unittest import mock

from aiogram import Bot
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("BOT_TOKEN", "123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567890")
os.environ.setdefault("GEMINI_API_KEY", "test_gemini_key")

import bot as bot_mod  # noqa: E402
import services as services_pkg  # noqa: E402
from tests.test_miniapp_api import ApiTestBase, fresh_init_data  # noqa: E402

SECRET = "test-secret_123"
BASE = "https://example.org"
HEADER = "X-Telegram-Bot-Api-Secret-Token"
PATH = bot_mod.WEBHOOK_PATH
UPDATE = {"update_id": 1, "message": {"message_id": 5, "text": "salom"}}


class FakeDispatcher:
    workflow_data: dict = {}

    def __init__(self):
        self.feed_raw_update = mock.AsyncMock(return_value=None)
        self.emit_startup = mock.AsyncMock()
        self.emit_shutdown = mock.AsyncMock()
        self.resolve_used_update_types = mock.MagicMock(return_value=["message", "callback_query"])


async def wait_awaited(m, times=1):
    for _ in range(300):
        if m.await_count >= times:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"{m} {times} marta await qilinmadi")


async def chunks(total, step=1024):
    """Content-Length'siz (chunked) tana."""
    sent = 0
    while sent < total:
        n = min(step, total - sent)
        yield b"x" * n
        sent += n


class SettingsTest(unittest.TestCase):
    def env(self, **kw):
        base = {k: v for k, v in os.environ.items() if k not in ("WEBHOOK_BASE_URL", "WEBHOOK_SECRET")}
        base.update(kw)
        return mock.patch.dict(os.environ, base, clear=True)

    def test_no_env_means_polling(self):
        with self.env():
            self.assertIsNone(bot_mod.get_webhook_settings())

    def test_empty_values_mean_polling(self):
        with self.env(WEBHOOK_BASE_URL="  ", WEBHOOK_SECRET=""):
            self.assertIsNone(bot_mod.get_webhook_settings())

    def test_only_one_of_two_means_polling_with_warning(self):
        for kw in ({"WEBHOOK_BASE_URL": BASE}, {"WEBHOOK_SECRET": SECRET}):
            with self.subTest(kw=kw), self.env(**kw), self.assertLogs(level="WARNING") as logs:
                self.assertIsNone(bot_mod.get_webhook_settings())
            self.assertNotIn(SECRET, "\n".join(logs.output))        # secret loglanmaydi

    def test_both_mean_webhook_and_trailing_slash_is_stripped(self):
        with self.env(WEBHOOK_BASE_URL=BASE + "/", WEBHOOK_SECRET=SECRET):
            self.assertEqual(bot_mod.get_webhook_settings(), (BASE, SECRET))

    def test_non_https_url_rejected(self):
        with self.env(WEBHOOK_BASE_URL="http://example.org", WEBHOOK_SECRET=SECRET):
            with self.assertRaises(RuntimeError):
                bot_mod.get_webhook_settings()

    def test_invalid_secret_rejected_without_leaking_it(self):
        bad = "yomon secret!"
        with self.env(WEBHOOK_BASE_URL=BASE, WEBHOOK_SECRET=bad):
            with self.assertRaises(RuntimeError) as cm:
                bot_mod.get_webhook_settings()
        self.assertNotIn(bad, str(cm.exception))


class WebhookRouteTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.dp = FakeDispatcher()
        self.tg_bot = Bot(token="123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567890")
        patches = [mock.patch.object(bot_mod, "dp", self.dp), mock.patch.object(bot_mod, "bot", self.tg_bot)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.client = TestClient(TestServer(bot_mod.create_web_app(webhook_secret=SECRET)))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)

    async def hook(self, body=None, headers=None, raw=None):
        data = raw if raw is not None else json.dumps(UPDATE if body is None else body)
        return await self.client.post(PATH, data=data, headers={"Content-Type": "application/json", **(headers or {})})

    async def test_no_secret_header_rejected(self):
        resp = await self.hook()
        self.assertIn(resp.status, (401, 403))
        await asyncio.sleep(0.05)
        self.dp.feed_raw_update.assert_not_awaited()

    async def test_wrong_secret_rejected(self):
        for value in ("wrong", SECRET + "x", SECRET[:-1], ""):
            with self.subTest(value=value):
                resp = await self.hook(headers={HEADER: value})
                self.assertIn(resp.status, (401, 403))
        await asyncio.sleep(0.05)
        self.dp.feed_raw_update.assert_not_awaited()

    async def test_non_ascii_secret_header_gives_401_not_500(self):
        resp = await self.hook(headers={HEADER: "maxfiy-é-ü"})
        self.assertEqual(resp.status, 401)
        self.dp.feed_raw_update.assert_not_awaited()

    async def test_correct_secret_accepted_and_update_fed(self):
        resp = await self.hook(headers={HEADER: SECRET})
        self.assertEqual(resp.status, 200)
        await wait_awaited(self.dp.feed_raw_update)
        kwargs = self.dp.feed_raw_update.await_args.kwargs
        self.assertEqual(kwargs["update"], UPDATE)
        self.assertIs(kwargs["bot"], self.tg_bot)

    async def test_update_bigger_than_old_16kb_limit_is_accepted(self):
        big = {"update_id": 2, "message": {"text": "x" * 100_000}}
        resp = await self.hook(body=big, headers={HEADER: SECRET})
        self.assertEqual(resp.status, 200)
        await wait_awaited(self.dp.feed_raw_update)
        self.assertEqual(self.dp.feed_raw_update.await_args.kwargs["update"], big)

    async def test_app_wide_limit_still_caps_webhook_body(self):
        huge = json.dumps({"update_id": 3, "pad": "x" * (bot_mod.WEB_MAX_BODY + 10)})
        resp = await self.hook(raw=huge, headers={HEADER: SECRET})
        self.assertEqual(resp.status, 413)
        self.dp.feed_raw_update.assert_not_awaited()

    async def test_no_api_rate_limit_and_no_init_data_needed(self):
        # /api/ rate-limit (20/daqiqa) va init_data tekshiruvi webhook'ga qo'llanmaydi
        total = bot_mod.API_RATE_LIMIT + 10
        for i in range(total):
            resp = await self.hook(body={"update_id": i}, headers={HEADER: SECRET})
            self.assertEqual(resp.status, 200, i)
        await wait_awaited(self.dp.feed_raw_update, total)

    async def test_only_post(self):
        for method in ("get", "put", "delete"):
            resp = await getattr(self.client, method)(PATH, headers={HEADER: SECRET})
            self.assertEqual(resp.status, 405, method)

    async def test_lifecycle_hooks_wired(self):
        # dp.startup/shutdown polling'dagidek ishlashi uchun setup_application ulangan
        self.dp.emit_startup.assert_awaited_once()
        await self.client.close()
        self.dp.emit_shutdown.assert_awaited_once()

    async def test_mini_app_api_still_protected_by_init_data(self):
        resp = await self.client.post("/api/state", json={"init_data": "buzuq"})
        self.assertEqual(resp.status, 403)


class RealDispatcherTest(unittest.IsolatedAsyncioTestCase):
    """Soxta emas, haqiqiy aiogram Dispatcher: webhook orqali kelgan Telegram update handlerga yetib boradi."""

    REAL_UPDATE = {
        "update_id": 77,
        "message": {"message_id": 5, "date": 1700000000, "chat": {"id": 1, "type": "private"},
                    "from": {"id": 1, "is_bot": False, "first_name": "Ali"}, "text": "salom webhook"},
    }

    async def test_update_reaches_handler_through_real_dispatcher(self):
        from aiogram import Dispatcher
        real_dp = Dispatcher()
        seen = []

        @real_dp.message()
        async def on_message(message):
            seen.append(message.text)

        with mock.patch.object(bot_mod, "dp", real_dp), \
             mock.patch.object(bot_mod, "bot", Bot(token="123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567890")):
            client = TestClient(TestServer(bot_mod.create_web_app(webhook_secret=SECRET)))
            await client.start_server()
        self.addAsyncCleanup(client.close)

        self.assertEqual(real_dp.resolve_used_update_types(), ["message"])
        bad = await client.post(PATH, json=self.REAL_UPDATE, headers={HEADER: "x"})
        self.assertEqual(bad.status, 401)
        good = await client.post(PATH, json=self.REAL_UPDATE, headers={HEADER: SECRET})
        self.assertEqual(good.status, 200)
        for _ in range(300):
            if seen:
                break
            await asyncio.sleep(0.01)
        self.assertEqual(seen, ["salom webhook"])               # rad etilgan so'rov handlerga yetmagan, to'g'risi yetgan


class NoWebhookByDefaultTest(unittest.IsolatedAsyncioTestCase):
    async def test_route_absent_without_secret(self):
        client = TestClient(TestServer(bot_mod.create_web_app()))
        await client.start_server()
        self.addAsyncCleanup(client.close)
        resp = await client.post(PATH, data="{}", headers={HEADER: SECRET, "Content-Type": "application/json"})
        self.assertEqual(resp.status, 404)

    def test_paths_registered_only_in_webhook_mode(self):
        def paths(app):
            return {r.resource.canonical for r in app.router.routes() if r.method == "POST"}
        self.assertNotIn(PATH, paths(bot_mod.create_web_app()))
        with mock.patch.object(bot_mod, "dp", FakeDispatcher()):
            self.assertIn(PATH, paths(bot_mod.create_web_app(webhook_secret=SECRET)))


class HandlerUnitTest(unittest.IsolatedAsyncioTestCase):
    def make(self, secret):
        return bot_mod.TelegramWebhookHandler(dispatcher=FakeDispatcher(), bot=mock.MagicMock(), secret_token=secret)

    def test_empty_secret_fails_closed(self):
        h = self.make("")
        self.assertFalse(h.verify_secret("", None))
        self.assertFalse(h.verify_secret("anything", None))

    def test_verify_secret(self):
        h = self.make(SECRET)
        self.assertTrue(h.verify_secret(SECRET, None))
        self.assertFalse(h.verify_secret("x", None))
        self.assertFalse(h.verify_secret("é", None))

    async def test_close_waits_for_in_flight_updates_then_closes_session(self):
        h = self.make(SECRET)
        h.bot.session.close = mock.AsyncMock()
        release = asyncio.Event()
        order = []

        async def slow_update():
            await release.wait()
            order.append("update_done")
        task = asyncio.create_task(slow_update())
        h._background_feed_update_tasks.add(task)
        h.bot.session.close.side_effect = lambda: order.append("session_closed")

        closing = asyncio.create_task(h.close())
        await asyncio.sleep(0.05)
        self.assertFalse(closing.done())                    # update tugamaguncha kutadi
        release.set()
        await asyncio.wait_for(closing, 2)
        self.assertEqual(order, ["update_done", "session_closed"])

    async def test_close_gives_up_after_grace_period(self):
        h = self.make(SECRET)
        h.bot.session.close = mock.AsyncMock()
        never = asyncio.create_task(asyncio.Event().wait())
        self.addCleanup(never.cancel)
        h._background_feed_update_tasks.add(never)
        with mock.patch.object(bot_mod, "WEBHOOK_SHUTDOWN_GRACE", 0.05):
            await asyncio.wait_for(h.close(), 2)
        h.bot.session.close.assert_awaited_once()


class BodyLimitTest(ApiTestBase):
    """Ilova limiti 1 MB ga ko'tarildi; /api/* route limitlari (4 KB / 16 KB) amalda o'zgarmasligi kerak."""

    def test_app_limit_raised_for_telegram_updates(self):
        app = bot_mod.create_web_app()
        self.assertGreaterEqual(app._client_max_size, 1024 * 1024)
        self.assertGreater(bot_mod.WEB_MAX_BODY, bot_mod.AI_CHAT_MAX_BODY)
        self.assertEqual(bot_mod.API_MAX_BODY, 4096)
        self.assertEqual(bot_mod.AI_CHAT_MAX_BODY, 16 * 1024)

    async def test_content_length_over_4kb_413_on_regular_routes(self):
        for path in ("/api/state", "/api/spin/claim", "/api/bonus/claim", "/api/invoice"):
            with self.subTest(path=path):
                raw = json.dumps({"init_data": fresh_init_data(), "pad": "x" * 5000})
                resp, data = await self.post(path, raw=raw)
                self.assertEqual((resp.status, data), (413, {"ok": False, "error": "payload_too_large"}))
        self.assert_no_db_calls()

    async def test_chunked_body_over_4kb_413_on_regular_routes(self):
        # Content-Length yo'q: 1 MB ilova limitiga tayanmasdan, route chegarasida to'xtashi kerak
        for path in ("/api/state", "/api/spin/claim", "/api/bonus/claim", "/api/invoice"):
            with self.subTest(path=path):
                resp = await self.client.post(path, data=chunks(64 * 1024),
                                              headers={"Content-Type": "application/json"})
                self.assertEqual(resp.status, 413)
                self.assertEqual(await resp.json(), {"ok": False, "error": "payload_too_large"})
        self.assert_no_db_calls()

    async def test_chunked_body_under_limit_still_works(self):
        raw = json.dumps({"init_data": fresh_init_data()}).encode()

        async def two_parts():
            yield raw[:10]
            yield raw[10:]
        resp = await self.client.post("/api/state", data=two_parts(), headers={"Content-Type": "application/json"})
        self.assertEqual(resp.status, 200)
        self.assertTrue((await resp.json())["ok"])

    async def test_ai_chat_keeps_its_own_16kb_limit(self):
        # 16 KB dan katta: ilova limiti (1 MB) ruxsat bersa ham route rad etadi (Content-Length bilan ham, chunked ham)
        resp, data = await self.post("/api/ai/chat", extra={"message": "x", "pad": "y" * 17000})
        self.assertEqual((resp.status, data["error"]), (400, "bad_request"))
        resp = await self.client.post("/api/ai/chat", data=chunks(64 * 1024),
                                      headers={"Content-Type": "application/json"})
        self.assertEqual(resp.status, 400)
        self.assertEqual((await resp.json())["error"], "bad_request")

    async def test_ai_chat_chunked_between_4kb_and_16kb_is_not_size_rejected(self):
        body = json.dumps({"init_data": fresh_init_data(), "message": "x", "pad": "y" * 6000}).encode()

        async def parts():
            for i in range(0, len(body), 2048):
                yield body[i:i + 2048]
        with mock.patch.object(bot_mod.database, "is_user_banned", return_value=(True, "")):
            resp = await self.client.post("/api/ai/chat", data=parts(), headers={"Content-Type": "application/json"})
        # Hajm o'tdi (initData tekshirildi) — keyingi bosqichda (ban) to'xtadi; 413/400 bo'lmasligi shart
        self.assertEqual(resp.status, 403)

    async def test_every_route_reads_body_through_bounded_reader_with_its_own_limit(self):
        # Ilova limiti 1 MB bo'lgani uchun xotira chegarasi route darajasida ta'minlanadi: o'qish
        # _read_body_limited orqali va aynan route chegarasi (4 KB / 16 KB) bilan bo'lishi shart.
        spy = mock.AsyncMock(side_effect=bot_mod._read_body_limited)
        expected = {"/api/state": 4096, "/api/spin/claim": 4096, "/api/bonus/claim": 4096,
                    "/api/invoice": 4096, "/api/ai/chat": 16 * 1024}
        with mock.patch.object(bot_mod, "_read_body_limited", spy):
            for path, limit in expected.items():
                with self.subTest(path=path):
                    spy.reset_mock()
                    await self.post(path, init_data="buzuq")            # 403: DB'ga tegmaydi
                    spy.assert_awaited_once()
                    self.assertEqual(spy.await_args.args[1], limit)
        self.assert_no_db_calls()

    async def test_read_body_limited_stops_reading_early(self):
        consumed = []

        class FakeContent:
            async def iter_chunked(self, n):
                for i in range(1000):
                    consumed.append(i)
                    yield b"x" * 1000

        request = mock.MagicMock(content=FakeContent())
        self.assertIsNone(await bot_mod._read_body_limited(request, 4096))
        self.assertLessEqual(len(consumed), 5)                      # 1000 ta bo'lakni o'qimaydi
        consumed.clear()
        self.assertEqual(await bot_mod._read_body_limited(mock.MagicMock(content=FakeContent()), 10**9),
                         b"x" * 1000 * 1000)


class ModeSelectionTest(unittest.IsolatedAsyncioTestCase):
    """main() env'ga qarab polling yoki webhook yo'lini tanlaydi; ikkala rejimda ham bir xil tayyorgarlik."""

    def patch_main(self, env):
        self.dp = mock.MagicMock()
        self.dp.start_polling = mock.AsyncMock()
        self.tg_bot = mock.MagicMock()
        self.tg_bot.delete_webhook = mock.AsyncMock()
        self.tg_bot.session.close = mock.AsyncMock()
        self.run_webhook = mock.AsyncMock()
        self.start_web = mock.AsyncMock()
        self.scheduler = mock.MagicMock()
        self.set_commands = mock.AsyncMock()
        self.reminders = mock.AsyncMock()
        clean = {k: v for k, v in os.environ.items() if k not in ("WEBHOOK_BASE_URL", "WEBHOOK_SECRET")}
        clean.update(env)
        fake_scheduler_module = types.SimpleNamespace(start_scheduler=self.scheduler)
        stack = [
            mock.patch.dict(os.environ, clean, clear=True),
            mock.patch.object(bot_mod, "dp", self.dp), mock.patch.object(bot_mod, "bot", self.tg_bot),
            mock.patch.object(bot_mod, "gemini_client", None),
            mock.patch.object(bot_mod.database, "init_db"),
            mock.patch.object(bot_mod.medicine_db, "init_medicine_db"),
            mock.patch.object(bot_mod, "set_bot_commands", self.set_commands),
            mock.patch.object(bot_mod, "check_and_send_reminders", self.reminders),
            mock.patch.object(bot_mod, "start_web_server", self.start_web),
            mock.patch.object(bot_mod, "run_webhook", self.run_webhook),
            # Haqiqiy modul APScheduler talab qiladi; test muhitida u bo'lmasligi mumkin — soxta modul qo'yiladi
            mock.patch.dict(sys.modules, {"services.engagement_scheduler": fake_scheduler_module}),
            mock.patch.object(services_pkg, "engagement_scheduler", fake_scheduler_module, create=True),
        ]
        for p in stack:
            p.start()
            self.addCleanup(p.stop)

    async def test_without_env_polling_is_used_as_before(self):
        self.patch_main({})
        await bot_mod.main()
        self.tg_bot.delete_webhook.assert_awaited_once_with(drop_pending_updates=False)
        self.dp.start_polling.assert_awaited_once_with(self.tg_bot)
        self.run_webhook.assert_not_awaited()
        await asyncio.sleep(0)                                     # create_task(start_web_server()) ishga tushsin
        self.start_web.assert_awaited_once_with()                  # polling'da web server avvalgidek (fon task)
        self.tg_bot.session.close.assert_awaited_once()

    async def test_with_env_webhook_is_used_and_polling_is_not(self):
        self.patch_main({"WEBHOOK_BASE_URL": BASE + "/", "WEBHOOK_SECRET": SECRET})
        await bot_mod.main()
        self.run_webhook.assert_awaited_once_with(BASE, SECRET)
        self.dp.start_polling.assert_not_awaited()
        self.tg_bot.delete_webhook.assert_not_awaited()            # webhook'ni o'chirmaymiz
        self.start_web.assert_not_awaited()                        # web server run_webhook ichida, alohida fon taskda emas
        self.tg_bot.session.close.assert_awaited_once()

    async def test_background_jobs_and_middlewares_same_in_both_modes(self):
        for env in ({}, {"WEBHOOK_BASE_URL": BASE, "WEBHOOK_SECRET": SECRET}):
            with self.subTest(webhook=bool(env)):
                self.patch_main(env)
                await bot_mod.main()
                await asyncio.sleep(0)
                self.set_commands.assert_awaited_once()
                self.reminders.assert_called_once()
                self.scheduler.assert_called_once()
                self.assertEqual(self.dp.message.outer_middleware.call_count, 3)
                self.assertEqual(self.dp.callback_query.outer_middleware.call_count, 3)

    async def test_invalid_webhook_config_fails_before_touching_database(self):
        self.patch_main({"WEBHOOK_BASE_URL": "http://example.org", "WEBHOOK_SECRET": SECRET})
        with self.assertRaises(RuntimeError):
            await bot_mod.main()
        bot_mod.database.init_db.assert_not_called()
        self.dp.start_polling.assert_not_awaited()

    async def test_webhook_start_failure_propagates_and_closes_session(self):
        self.patch_main({"WEBHOOK_BASE_URL": BASE, "WEBHOOK_SECRET": SECRET})
        self.run_webhook.side_effect = RuntimeError("set_webhook yiqildi")
        with self.assertRaises(RuntimeError):
            await bot_mod.main()
        self.tg_bot.session.close.assert_awaited_once()


class RunWebhookTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.runner = mock.MagicMock()
        self.runner.cleanup = mock.AsyncMock()
        self.dp = FakeDispatcher()
        self.tg_bot = mock.MagicMock()
        self.tg_bot.set_webhook = mock.AsyncMock()
        self.tg_bot.delete_webhook = mock.AsyncMock()
        self.start_web = mock.AsyncMock(return_value=self.runner)
        for p in (mock.patch.object(bot_mod, "dp", self.dp), mock.patch.object(bot_mod, "bot", self.tg_bot),
                  mock.patch.object(bot_mod, "start_web_server", self.start_web)):
            p.start()
            self.addCleanup(p.stop)

    async def test_sets_webhook_then_stays_alive_and_never_deletes_it(self):
        task = asyncio.create_task(bot_mod.run_webhook(BASE, SECRET))
        await wait_awaited(self.tg_bot.set_webhook)
        self.start_web.assert_awaited_once_with(webhook_secret=SECRET)
        self.tg_bot.set_webhook.assert_awaited_once_with(
            url=f"{BASE}/api/tg/webhook", secret_token=SECRET,
            allowed_updates=["message", "callback_query"], drop_pending_updates=False)
        await asyncio.sleep(0.05)
        self.assertFalse(task.done())                              # jarayon tirik qoladi (polling yo'q)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.runner.cleanup.assert_awaited_once()                  # server to'xtatiladi (update'lar kutiladi)
        self.tg_bot.delete_webhook.assert_not_awaited()            # shutdown'da webhook o'chirilmaydi

    async def test_web_server_started_before_set_webhook(self):
        order = []
        self.start_web.side_effect = lambda **kw: (order.append("server"), self.runner)[1]
        self.tg_bot.set_webhook.side_effect = lambda **kw: order.append("set_webhook")
        task = asyncio.create_task(bot_mod.run_webhook(BASE, SECRET))
        await wait_awaited(self.tg_bot.set_webhook)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(order, ["server", "set_webhook"])

    async def test_set_webhook_error_still_cleans_up_server(self):
        self.tg_bot.set_webhook.side_effect = RuntimeError("telegram rad etdi")
        with self.assertRaises(RuntimeError):
            await bot_mod.run_webhook(BASE, SECRET)
        self.runner.cleanup.assert_awaited_once()


class StartWebServerTest(unittest.IsolatedAsyncioTestCase):
    async def test_passes_secret_to_app_and_returns_runner(self):
        runner = mock.MagicMock()
        runner.setup = mock.AsyncMock()
        site = mock.MagicMock()
        site.start = mock.AsyncMock()
        with mock.patch.object(bot_mod, "create_web_app") as create, \
             mock.patch.object(bot_mod.web, "AppRunner", return_value=runner), \
             mock.patch.object(bot_mod.web, "TCPSite", return_value=site) as tcp_site, \
             mock.patch.dict(os.environ, {"PORT": "19998"}):
            result = await bot_mod.start_web_server(webhook_secret=SECRET)
        create.assert_called_once_with(SECRET)
        self.assertIs(result, runner)
        self.assertEqual(tcp_site.call_args.args[1:], ("127.0.0.1", 19998))     # webhook rejimida ham faqat localhost

    async def test_default_has_no_webhook(self):
        runner = mock.MagicMock()
        runner.setup = mock.AsyncMock()
        site = mock.MagicMock()
        site.start = mock.AsyncMock()
        with mock.patch.object(bot_mod, "create_web_app") as create, \
             mock.patch.object(bot_mod.web, "AppRunner", return_value=runner), \
             mock.patch.object(bot_mod.web, "TCPSite", return_value=site):
            await bot_mod.start_web_server()
        create.assert_called_once_with(None)


if __name__ == "__main__":
    unittest.main()
