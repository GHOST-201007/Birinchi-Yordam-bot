"""
e2e_base.py — Mini App brauzer (Playwright) testlari uchun umumiy asos.

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
  const state = { closed: 0, links: [], alerts: [], invoices: [], backVisible: false, headerColors: [], bgColors: [] };
  window.__tg = state;
  const noop = () => {};
  window.Telegram = { WebApp: {
    initData: %(init)s,
    initDataUnsafe: { user: { id: 424242, first_name: 'Ali' } },
    version: '8.0', platform: 'tdesktop', colorScheme: 'light', themeParams: {},
    ready: noop, expand: noop, disableVerticalSwipes: noop,
    setHeaderColor: (c) => { state.headerColors.push(c); }, setBackgroundColor: (c) => { state.bgColors.push(c); },
    onEvent: (name, cb) => { (window.__tgEvents = window.__tgEvents || {})[name] = cb; },
    offEvent: noop, enableClosingConfirmation: noop, sendData: noop,
    isVersionAtLeast: () => true,
    close: () => { state.closed++; },
    openTelegramLink: (u) => { state.links.push(u); },
    showAlert: (m) => { state.alerts.push(m); },
    openInvoice: (u, cb) => { state.invoices.push(u); window.__invoiceCb = cb; },
    HapticFeedback: { impactOccurred: noop, notificationOccurred: noop, selectionChanged: noop },
    CloudStorage: {
      getItem: (k, cb) => cb && cb(null, ''), setItem: (k, v, cb) => cb && cb(null, true),
      removeItem: (k, cb) => cb && cb(null, true), getKeys: (cb) => cb && cb(null, []),
      getItems: (ks, cb) => cb && cb(null, {})
    },
    BackButton: { show: () => { state.backVisible = true; }, hide: () => { state.backVisible = false; },
                  onClick: (cb) => { window.__backCb = cb; }, offClick: noop },
    MainButton: { show: noop, hide: noop, setText: noop, onClick: noop, offClick: noop }
  } };
})();
"""

def sequence(*specs):
    """Har bir chaqiruvga ketma-ket bittadan javob beradi (oxirgisi takrorlanadi).
    Javob: (status, json) | "abort" | "hang" (so'rov javobsiz osilib qoladi — sekin server taqlidi)."""
    counter = {"i": 0}

    def next_spec(_body):
        spec = specs[min(counter["i"], len(specs) - 1)]
        counter["i"] += 1
        return spec

    return next_spec


STATE_OK = {"ok": True, "score": 7, "streak": 1, "daily_claimed": False, "prize": 5, "cooldown_seconds": 0}
CLAIM_OK = {"ok": True, "message": "Tabriklaymiz! +5 ball", "score": 12, "is_super": False}


@unittest.skipIf(sync_playwright is None, "playwright o'rnatilmagan")
class MiniAppE2EBase(unittest.TestCase):
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
    def open_app(self, routes, query="", init_data=INIT_DATA, init_script=""):
        """routes: {'state': (status, json) | 'abort' | 'hang' | callable(body) -> shulardan biri, ...}.
        Qaytaradi: (page, calls)."""
        ctx = self.browser.new_context(viewport={"width": 390, "height": 844})
        self.addCleanup(ctx.close)
        page = ctx.new_page()
        self.page_for_wait = page
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
                if callable(spec):
                    spec = spec(body)
                if spec == "abort":
                    return route.abort()
                if spec == "hang":
                    return          # javob berilmaydi: sahifadagi 8 s timeout (soat) ishlaguncha osilib turadi
                status, data = spec
                return route.fulfill(status=status, content_type="application/json", body=json.dumps(data))
            if url.startswith(f"http://127.0.0.1:{self.port}"):
                return route.continue_()
            return route.abort()          # tashqi manbalar (shrift, FontAwesome, telegram.org) bloklanadi

        page.route("**/*", handle)
        page.add_init_script(FAKE_TELEGRAM % {"init": json.dumps(init_data)})
        if init_script:
            page.add_init_script(init_script)         # fake Telegram'dan KEYIN: masalan, openInvoice ni olib tashlash
        page.clock.install()
        page.goto(f"http://127.0.0.1:{self.port}/{query}", wait_until="load")
        return page, calls

    def wait_for_call(self, calls, name, timeout_s=10):
        """So'rov serverga yetib kelguncha kutadi (haqiqiy vaqt; sahifa soatiga bog'liq emas)."""
        import time as _t
        end = _t.time() + timeout_s
        while _t.time() < end:
            if any(c[0] == name for c in calls):
                return
            self.page_for_wait.wait_for_timeout(50)
        raise AssertionError(f"/api/{name} so'rovi kelmadi")

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
