"""
test_miniapp_wheel_e2e.py — Mini App baraboni /api/ orqali aylantirish (4-qadam), brauzerda (Playwright).

Telegram WebApp obyekti va /api/* javoblari taqlid qilinadi; tashqi tarmoq bloklanadi.
Playwright yoki Chromium o'rnatilmagan bo'lsa testlar o'tkazib yuboriladi.
"""
import functools
import json
import os
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(PROJECT_DIR, "app")
sys.path.insert(0, PROJECT_DIR)

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

import app_server  # noqa: E402

INIT_DATA = "query_id=AAH-test&user=%7B%22id%22%3A424242%7D&auth_date=1800000000&hash=deadbeef"

FAKE_TELEGRAM = """
(() => {
  const state = { closed: 0, links: [], alerts: [] };
  window.__tg = state;
  const noop = () => {};
  window.Telegram = { WebApp: {
    initData: %(init)s,
    initDataUnsafe: { user: { id: 424242, first_name: 'Ali' } },
    version: '8.0', platform: 'tdesktop', colorScheme: 'light', themeParams: {},
    ready: noop, expand: noop, disableVerticalSwipes: noop, setHeaderColor: noop, setBackgroundColor: noop,
    onEvent: noop, offEvent: noop, enableClosingConfirmation: noop, sendData: noop,
    isVersionAtLeast: () => true,
    close: () => { state.closed++; },
    openTelegramLink: (u) => { state.links.push(u); },
    showAlert: (m) => { state.alerts.push(m); },
    HapticFeedback: { impactOccurred: noop, notificationOccurred: noop, selectionChanged: noop },
    CloudStorage: {
      getItem: (k, cb) => cb && cb(null, ''), setItem: (k, v, cb) => cb && cb(null, true),
      removeItem: (k, cb) => cb && cb(null, true), getKeys: (cb) => cb && cb(null, []),
      getItems: (ks, cb) => cb && cb(null, {})
    },
    BackButton: { show: noop, hide: noop, onClick: noop, offClick: noop },
    MainButton: { show: noop, hide: noop, setText: noop, onClick: noop, offClick: noop }
  } };
})();
"""

STATE_OK = {"ok": True, "score": 7, "streak": 1, "daily_claimed": False, "prize": 5, "cooldown_seconds": 0}
CLAIM_OK = {"ok": True, "message": "Tabriklaymiz! +5 ball", "score": 12, "is_super": False}


@unittest.skipIf(sync_playwright is None, "playwright o'rnatilmagan")
class WheelApiE2ETest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handler = functools.partial(app_server.MiniAppHandler, directory=APP_DIR)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.pw = sync_playwright().start()
        try:
            cls.browser = cls.pw.chromium.launch()
        except Exception as exc:  # pragma: no cover
            cls.pw.stop()
            cls.server.shutdown()
            raise unittest.SkipTest(f"Chromium ishga tushmadi: {exc}")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.shutdown()
        cls.server.server_close()

    # ---- yordamchilar -------------------------------------------------------
    def open_app(self, routes, query="", init_data=INIT_DATA):
        """routes: {'state': (status, json) | 'abort', ...}. Qaytaradi: (page, calls)."""
        ctx = self.browser.new_context(viewport={"width": 390, "height": 844})
        self.addCleanup(ctx.close)
        page = ctx.new_page()
        calls = []
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        self.addCleanup(lambda: self.assertEqual(errors, [], f"sahifada xato: {errors}"))

        def handle(route):
            url = route.request.url
            if url.startswith(f"http://127.0.0.1:{self.port}/api/"):
                name = url.split("/api/", 1)[1]
                body = route.request.post_data_json if route.request.method == "POST" else None
                calls.append((name, body))
                spec = routes.get(name, (404, {"ok": False}))
                if spec == "abort":
                    return route.abort()
                status, data = spec
                return route.fulfill(status=status, content_type="application/json", body=json.dumps(data))
            if url.startswith(f"http://127.0.0.1:{self.port}"):
                return route.continue_()
            return route.abort()          # tashqi manbalar (shrift, FontAwesome, telegram.org) bloklanadi

        page.route("**/*", handle)
        page.add_init_script(FAKE_TELEGRAM % {"init": json.dumps(init_data)})
        page.clock.install()
        page.goto(f"http://127.0.0.1:{self.port}/{query}", wait_until="load")
        return page, calls

    def open_wheel(self, page):
        page.click("#btn-open-wheel")
        page.wait_for_function("document.querySelector('#wheel-modal').style.display === 'flex'")

    def spin_and_finish(self, page):
        page.click("#btn-spin-wheel")
        page.clock.fast_forward(6000)       # 5.3 soniyalik animatsiya taymerini ishga tushiradi
        page.wait_for_selector("#btn-confirm-spin")

    def spin_and_confirm(self, page):
        self.spin_and_finish(page)
        page.click("#btn-confirm-spin")

    def tg(self, page):
        return page.evaluate("window.__tg")

    def card_text(self, page):
        return page.inner_text("#wheel-result-msg")

    # ---- API orqali oqim ------------------------------------------------------
    def test_spin_claim_via_api_no_bot_redirect(self):
        page, calls = self.open_app({"state": (200, STATE_OK), "spin/claim": (200, CLAIM_OK)})
        self.open_wheel(page)
        page.wait_for_function("document.querySelector('#global-score-val').textContent === '7'")
        self.assertFalse(page.is_disabled("#btn-spin-wheel"))
        self.spin_and_finish(page)
        self.assertEqual([c[0] for c in calls], ["state"])           # tugma bosilguncha ball qo'shilmaydi
        page.click("#btn-confirm-spin")
        page.wait_for_function("document.querySelector('#global-score-val').textContent === '12'")

        self.assertIn("+5 ball hisobingizga qo'shildi", self.card_text(page))
        self.assertEqual([c[0] for c in calls], ["state", "spin/claim"])
        for _, body in calls:
            self.assertEqual(body, {"init_data": INIT_DATA})        # tanada boshqa hech narsa yo'q
        tg = self.tg(page)
        self.assertEqual(tg["closed"], 0)                           # tg.close() chaqirilmaydi
        self.assertEqual(tg["links"], [])                           # botga chiqilmaydi

    def test_menu_button_open_without_url_params_works(self):
        # Menyu tugmasidan ochilganda URL'da hech narsa yo'q (prize/score yo'q) — API yetarli
        page, _ = self.open_app({"state": (200, STATE_OK), "spin/claim": (200, CLAIM_OK)}, query="")
        self.open_wheel(page)
        page.wait_for_function("!document.querySelector('#btn-spin-wheel').disabled")
        self.spin_and_confirm(page)
        page.wait_for_selector("#wheel-result-msg .result-desc:has-text('hisobingizga qo')")
        self.assertNotIn("Bot orqali kiring", self.card_text(page))

    def test_super_prize_offers_discount_button(self):
        page, _ = self.open_app({
            "state": (200, {**STATE_OK, "prize": 0}),
            "spin/claim": (200, {"ok": True, "message": "SUPER", "score": 7, "is_super": True}),
        })
        self.open_wheel(page)
        page.wait_for_function("!document.querySelector('#btn-spin-wheel').disabled")
        self.spin_and_confirm(page)
        page.wait_for_selector("#wheel-result-msg .result-desc:has-text('50% chegirma faollashtirildi')")
        self.assertEqual(self.tg(page)["closed"], 0)
        self.assertEqual(self.tg(page)["links"], [])
        page.click("#wheel-result-msg .result-confirm-btn")            # "Premium olish"
        tg = self.tg(page)
        self.assertEqual(tg["links"], ["https://t.me/Birinchiyordam1Bot?start=buy_plus_30"])
        self.assertEqual(tg["closed"], 0)

    def test_cooldown_from_server_blocks_spin_and_shows_timer(self):
        page, calls = self.open_app({"state": (200, {**STATE_OK, "prize": None, "cooldown_seconds": 3600})})
        self.open_wheel(page)
        page.wait_for_selector("#wheel-countdown-timer")
        self.assertEqual(page.inner_text("#wheel-countdown-timer"), "01:00:00")
        self.assertTrue(page.is_disabled("#btn-spin-wheel"))
        self.assertEqual(page.inner_text("#btn-spin-wheel .wheel-center-text"), "KUTISH")
        self.assertEqual([c[0] for c in calls], ["state"])

    def test_claim_not_ok_shows_server_message_and_updates_score(self):
        page, _ = self.open_app({
            "state": (200, STATE_OK),
            "spin/claim": (200, {"ok": False, "message": "Allaqachon olingan", "score": 9, "is_super": False}),
        })
        self.open_wheel(page)
        page.wait_for_function("!document.querySelector('#btn-spin-wheel').disabled")
        self.spin_and_confirm(page)
        page.wait_for_selector("#wheel-result-msg .result-title:has-text('Ball qo')")
        self.assertIn("Allaqachon olingan", self.card_text(page))
        self.assertEqual(page.inner_text("#global-score-val"), "9")

    def test_server_message_is_not_interpreted_as_html(self):
        evil = "<img src=x onerror=\"window.__xss=1\"><b>qalin</b>"
        page, _ = self.open_app({
            "state": (200, STATE_OK),
            "spin/claim": (200, {"ok": False, "message": evil, "score": 1, "is_super": False}),
        })
        self.open_wheel(page)
        page.wait_for_function("!document.querySelector('#btn-spin-wheel').disabled")
        self.spin_and_confirm(page)
        page.wait_for_selector("#wheel-result-msg .result-title:has-text('Ball qo')")
        self.assertIn("<b>qalin</b>", self.card_text(page))             # matn sifatida ko'rinadi
        self.assertEqual(page.locator("#wheel-result-msg img").count(), 0)
        self.assertIsNone(page.evaluate("window.__xss"))

    # ---- ZAXIRA yo'l (eski URL-parametr + deep link mantig'i) --------------------
    def test_fallback_when_state_api_fails_uses_url_prize_and_deep_link(self):
        page, calls = self.open_app({"state": (500, {"ok": False, "error": "server_error"})},
                                    query="?prize=5&score=3")
        self.open_wheel(page)
        page.wait_for_function("!document.querySelector('#btn-spin-wheel').disabled")
        self.assertEqual(page.inner_text("#global-score-val"), "3")     # URL'dagi ball
        self.spin_and_finish(page)
        self.assertEqual([c[0] for c in calls], ["state"])               # claim chaqirilmadi
        page.click("#btn-confirm-spin")
        tg = self.tg(page)
        self.assertEqual(tg["links"], ["https://t.me/Birinchiyordam1Bot?start=spin_5"])
        self.assertEqual(tg["closed"], 1)

    def test_fallback_when_no_init_data_makes_no_api_calls(self):
        page, calls = self.open_app({}, query="?prize=3", init_data="")
        self.open_wheel(page)
        page.wait_for_function("!document.querySelector('#btn-spin-wheel').disabled")
        self.spin_and_finish(page)
        page.click("#btn-confirm-spin")
        self.assertEqual(calls, [])
        self.assertEqual(self.tg(page)["links"], ["https://t.me/Birinchiyordam1Bot?start=spin_3"])

    def test_fallback_without_url_prize_asks_to_use_bot(self):
        page, _ = self.open_app({"state": "abort"}, query="")
        self.open_wheel(page)
        page.wait_for_function("!document.querySelector('#btn-spin-wheel').disabled")
        page.click("#btn-spin-wheel")
        page.wait_for_selector("#btn-open-bot-wheel")
        self.assertIn("Bot orqali kiring", self.card_text(page))

    def test_claim_network_failure_falls_back_to_deep_link(self):
        page, calls = self.open_app({"state": (200, STATE_OK), "spin/claim": "abort"})
        self.open_wheel(page)
        page.wait_for_function("!document.querySelector('#btn-spin-wheel').disabled")
        self.spin_and_confirm(page)
        page.wait_for_function("window.__tg.links.length === 1")
        self.assertEqual([c[0] for c in calls], ["state", "spin/claim"])
        self.assertEqual(self.tg(page)["links"], ["https://t.me/Birinchiyordam1Bot?start=spin_5"])
        self.assertEqual(self.tg(page)["closed"], 1)


if __name__ == "__main__":
    unittest.main()
