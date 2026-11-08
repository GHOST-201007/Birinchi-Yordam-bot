"""
test_miniapp_csp.py — redesign 4.5–4.7: a11y / CSP.
- index.html va app.js da inline style / inline hodisa atributlari (onclick=...) yo'q
- viewport: kattalashtirish taqiqlanmagan (user-scalable=no, maximum-scale yo'q)
- app_server Content-Security-Policy yuboradi: faqat kerakli manbalar, Telegram WebApp SDK ruxsat etilgan
- Brauzerda CSP yoqilgan holda asosiy ekran va oynalar xatosiz ishlaydi (e2e_base CSP buzilishini xato deb oladi)
"""
import os
import re
import unittest
import urllib.request

from tests.e2e_base import STATE_OK, MiniAppE2EBase

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class InlineCodeStaticTest(unittest.TestCase):
    def test_index_has_no_inline_styles_or_handlers(self):
        html = read("app/index.html")
        self.assertNotRegex(html, r"\sstyle\s*=")
        self.assertNotRegex(html, r"\son[a-z]+\s*=\s*[\"']")
        self.assertEqual(re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", html), [])      # inline script yo'q

    def test_js_templates_have_no_inline_styles_or_handlers(self):
        js = read("app/app.js")
        self.assertNotRegex(js, r"""\sstyle=\\?["']""")
        self.assertNotRegex(js, r"""\son(click|load|error|change|input|submit)=\\?["']""")
        self.assertNotIn("setAttribute('style'", js)
        self.assertNotIn("eval(", js)
        self.assertNotIn("new Function", js)

    def test_viewport_allows_zoom(self):
        meta = re.search(r'<meta name="viewport" content="([^"]+)"', read("app/index.html")).group(1)
        self.assertNotIn("user-scalable", meta)
        self.assertNotIn("maximum-scale", meta)
        self.assertIn("width=device-width", meta)


class CspHeaderE2ETest(MiniAppE2EBase):
    def csp(self, path="/"):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}") as r:
            return r.headers.get("Content-Security-Policy")

    def test_header_on_index_and_assets(self):
        for path in ("/", "/app.js", "/style.css"):
            self.assertTrue(self.csp(path), path)
        policy = dict(d.strip().split(" ", 1) for d in self.csp().split(";"))
        self.assertEqual(policy["default-src"], "'self'")
        self.assertEqual(policy["script-src"], "'self' https://telegram.org")       # Telegram WebApp SDK
        self.assertEqual(policy["style-src"], "'self'")
        self.assertEqual(policy["connect-src"], "'self'")
        self.assertEqual(policy["object-src"], "'none'")
        self.assertIn("https://web.telegram.org", policy["frame-ancestors"])
        for d in policy.values():
            self.assertNotIn("unsafe-inline", d)
            self.assertNotIn("unsafe-eval", d)
            self.assertNotIn("*;", d + ";")

    def test_inline_style_is_blocked_by_policy(self):
        # Siyosat haqiqatan ishlaydi: inline style atributi qo'llanmaydi. Ataylab buzilish chiqargani uchun
        # open_app (u CSP buzilishini xato deb oladi) emas — alohida sahifa; tashqi so'rovlar bloklanadi.
        ctx = self.browser.new_context()
        self.addCleanup(ctx.close)
        page = ctx.new_page()
        page.route("**/*", lambda r: r.continue_() if r.request.url.startswith(f"http://127.0.0.1:{self.port}") else r.abort())
        violations = []
        page.on("console", lambda m: violations.append(m.text) if "Content Security Policy" in m.text else None)
        page.goto(f"http://127.0.0.1:{self.port}/", wait_until="load")
        page.evaluate("""() => { document.body.insertAdjacentHTML('beforeend', '<div id="csp-probe" style="width:123px"></div>'); }""")
        page.wait_for_timeout(100)
        self.assertNotEqual(page.evaluate("getComputedStyle(document.getElementById('csp-probe')).width"), "123px")
        self.assertTrue(violations)

    def test_screens_and_sheets_work_under_csp(self):
        # CSP yoqilgan (bypass yo'q); eval ishlatadigan wait_for_function o'rniga selektor/vaqt kutish
        page, _ = self.open_app({"state": (200, {**STATE_OK, "is_premium": False, "premium_type": "free"})},
                                enforce_csp=True)
        page.wait_for_selector("#global-score:not([hidden])")
        self.assertEqual(page.inner_text("#global-score-val"), "7")
        for tab in ("tab-diseases", "tab-health", "tab-body-map", "tab-first-aid"):
            page.click(f'nav [data-tab="{tab}"]')
            page.wait_for_selector(f"#{tab}.active")
        page.click('#first-aid-grid [data-id="kuyish"]')
        page.wait_for_selector("#overlay-details.active")
        page.evaluate("window.__backCb()")
        page.clock.fast_forward(400)
        page.click("#btn-open-wheel")
        page.wait_for_selector("#wheel-modal:not(.hidden)")
        self.assertEqual(page.evaluate("document.querySelector('#wheel-modal').style.display"), "flex")   # CSSOM ishlaydi
        page.click("#wheel-modal-close")
        page.click("#btn-open-daily-bonus")
        page.wait_for_selector("#daily-bonus-modal:not(.hidden)")
        page.click("#daily-bonus-close")
        page.click("#btn-open-premium")
        page.wait_for_selector("#premium-modal:not(.hidden)")
        page.wait_for_timeout(200)
        # sahifa xatolari va CSP buzilishlari e2e_base cleanup'ida tekshiriladi (bo'sh bo'lishi shart)

if __name__ == "__main__":
    unittest.main()
