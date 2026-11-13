"""
test_miniapp_ban_screen_e2e.py — Mini App (brauzerda / Playwright): bloklangan foydalanuvchi va server xatosi ekranlari.

  * 📣 OCHIQ ban: server 403 {"error":"banned","until","reason","contact"} -> to'liq ekranli "Siz bloklangansiz" (ikonka sprite'dan,
    muddat, sabab, murojaat). Boshqa tablar, tugmalar, MainButton / BackButton, botga o'tkazuvchi havolalar ishlamaydi.
  * 🤫 SIRLI ban serverda oddiy server xatosi: ilova ochilishida /api/state `server_error` qaytarsa — "Xatolik yuz berdi" ekrani.
    Ekran ban uchun alohida EMAS (hamma server xatolari uchun) va ban haqida bir og'iz ham aytmaydi.
Asos: tests/e2e_base.py
"""
import os
import re
import unittest

from tests.e2e_base import CONTRAST_JS, STATE_OK, MiniAppE2EBase

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANNED = (403, {"ok": False, "error": "banned", "until": "2026-11-20T14:00:00+05:00", "reason": "Spam",
                "contact": "@adminbot"})
BANNED_FOREVER = (403, {"ok": False, "error": "banned", "until": None, "reason": None, "contact": None})
SERVER_ERROR = (500, {"ok": False, "error": "server_error"})


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


class BanScreenE2ETest(MiniAppE2EBase):
    def open_banned(self, spec=BANNED, **kw):
        page, calls = self.open_app({"state": spec}, **kw)
        page.wait_for_selector("#ban-screen:not([hidden])")
        return page, calls

    def texts(self, page):
        return page.evaluate("""() => { const vis = (id) => { const e = document.getElementById(id); return e.hidden ? null : e.textContent; };
            return { title: vis('ban-title'), until: vis('ban-until'), reason: vis('ban-reason'), contact: vis('ban-contact') }; }""")

    # ---- ochiq ban: ekran ----------------------------------------------------------------
    def test_open_ban_screen_shows_term_reason_and_contact(self):
        page, _ = self.open_banned()
        self.assertEqual(self.texts(page), {"title": "Siz bloklangansiz", "until": "Muddat: 20.11.2026 14:00 gacha",
                                           "reason": "Sabab: Spam", "contact": "Murojaat uchun: @adminbot"})
        self.assertEqual(page.get_attribute("#ban-screen .block-icon use", "href"), "#i-ban")            # sprite, emoji emas
        self.assertTrue(page.is_hidden("#error-screen"))
        self.assertEqual(page.get_attribute("#ban-screen", "role"), "alertdialog")

    def test_permanent_ban_without_reason_or_contact(self):
        page, _ = self.open_banned(BANNED_FOREVER)
        self.assertEqual(self.texts(page), {"title": "Siz bloklangansiz", "until": "Muddat: ♾ muddatsiz", "reason": None,
                                           "contact": "Murojaat uchun administratorga yozing."})

    def test_reason_is_text_not_html(self):
        page, _ = self.open_banned((403, {**BANNED[1], "reason": '<b>x</b><img src=x onerror="window.__xss=1">'}))
        self.assertIn("<b>x</b>", page.inner_text("#ban-reason"))
        self.assertEqual(page.evaluate("document.querySelectorAll('#ban-reason *').length"), 0)
        self.assertIsNone(page.evaluate("window.__xss"))

    def test_the_screen_covers_everything_and_the_rest_of_the_app_is_dead(self):
        page, _ = self.open_banned()
        geo = page.evaluate("""() => { const b = document.getElementById('ban-screen').getBoundingClientRect();
            const nav = document.querySelector('nav [data-tab="tab-ai"]').getBoundingClientRect();
            const top = document.elementFromPoint(nav.left + nav.width / 2, nav.top + nav.height / 2);
            return { w: b.width, h: b.height, vw: window.innerWidth, vh: window.innerHeight,
                     onTop: !!top.closest('#ban-screen'),
                     inert: [...document.body.children].filter((e) => e.tagName !== 'SCRIPT'
                         && !['ban-screen', 'error-screen'].includes(e.id)).every((e) => e.inert) }; }""")
        self.assertEqual((geo["w"], geo["h"]), (geo["vw"], geo["vh"]))
        self.assertTrue(geo["onTop"])                                       # tab tugmasi o'rnida ham ban ekrani
        self.assertTrue(geo["inert"])                                       # qolgan hamma narsa inert
        with self.assertRaises(Exception):                                  # tab bosilmaydi
            page.click('nav [data-tab="tab-ai"]', timeout=1500)
        tg = self.tg(page)
        self.assertFalse(tg["mainVisible"])
        self.assertFalse(tg["backVisible"])

    def test_telegram_buttons_and_bot_links_stay_dead(self):
        page, _ = self.open_banned()
        page.evaluate("""() => { window.Telegram.WebApp.openTelegramLink('https://t.me/Birinchiyordam1Bot?start=buy_pro_7');
                                 window.__tgMain = window.Telegram.WebApp.MainButton; }""")
        self.assertEqual(self.tg(page)["links"], [])                        # botga zaxira havolalari ochilmaydi
        page.evaluate("MainButtonCtl.set({ text: 'X', owner: 'test', onClick: () => {} })")
        self.assertFalse(self.tg(page)["mainVisible"])

    def test_ban_discovered_later_in_the_session_locks_the_app(self):
        page, _ = self.open_app({"state": (200, STATE_OK), "bonus/claim": BANNED})
        page.wait_for_selector("#global-score:not([hidden])")
        self.assertTrue(page.is_hidden("#ban-screen"))
        page.evaluate("() => api('bonus/claim').catch(() => null)")
        page.wait_for_selector("#ban-screen:not([hidden])")
        self.assertEqual(self.texts(page)["until"], "Muddat: 20.11.2026 14:00 gacha")

    def test_ai_chat_403_banned_also_shows_the_screen(self):
        page, _ = self.open_app({"state": (200, STATE_OK), "ai/chat": BANNED})
        page.wait_for_selector("#global-score:not([hidden])")
        page.evaluate("() => api('ai/chat', { message: 'x' }, { withStatus: true })")
        page.wait_for_selector("#ban-screen:not([hidden])")

    def test_other_403_errors_do_not_show_the_ban_screen(self):
        page, _ = self.open_app({"state": (403, {"ok": False, "error": "forbidden"})})
        page.wait_for_timeout(600)
        self.assertTrue(page.is_hidden("#ban-screen"))
        self.assertTrue(page.is_hidden("#error-screen"))

    # ---- sirli ban: oddiy xato ekrani -----------------------------------------------------
    def test_silent_ban_shows_the_plain_error_screen_and_says_nothing_about_a_ban(self):
        page, _ = self.open_app({"state": SERVER_ERROR})
        page.wait_for_selector("#error-screen:not([hidden])")
        self.assertEqual(page.inner_text("#error-title"), "Xatolik yuz berdi")
        self.assertIn("Keyinroq urinib ko'ring.", page.inner_text("#error-screen"))
        self.assertEqual(page.inner_text("#error-retry"), "Qayta urinish")
        self.assertEqual(page.get_attribute("#error-screen .block-icon use", "href"), "#i-alert-triangle")
        self.assertTrue(page.is_hidden("#ban-screen"))
        visible = page.evaluate("document.getElementById('error-screen').innerText").lower()
        for word in ("ban", "blok", "bloklan", "chetlash", "sabab", "muddat"):
            self.assertNotIn(word, visible)
        self.assertIn("103", visible)                                       # shoshilinch raqam ko'rinib turadi
        page.evaluate("1")
        self.assertTrue(page.evaluate("[...document.body.children].filter((e) => e.tagName !== 'SCRIPT' "
                                      "&& !['ban-screen', 'error-screen'].includes(e.id)).every((e) => e.inert)"))

    def test_error_screen_is_the_same_for_any_server_error(self):
        """Ban uchun alohida emas: har qanday server xatosi (ochilishda) shu ekranni beradi."""
        for status in (500, 503):
            with self.subTest(status=status):
                page, _ = self.open_app({"state": (status, {"ok": False, "error": "server_error"})})
                page.wait_for_selector("#error-screen:not([hidden])")

    def test_retry_reloads_and_asks_the_server_again(self):
        page, calls = self.open_app({"state": SERVER_ERROR})
        page.wait_for_selector("#error-screen:not([hidden])")
        page.click("#error-retry")
        for _ in range(100):
            if [c[0] for c in calls].count("state") >= 2:
                break
            page.wait_for_timeout(100)
        self.assertGreaterEqual([c[0] for c in calls].count("state"), 2)

    def test_gateway_failures_without_a_server_code_keep_the_degraded_mode(self):
        """nginx 502 (JSON'siz) yoki tarmoq uzilishi: eski zaxira rejimi (ilova ishlaydi, xato ekrani yo'q)."""
        for spec in ((502, {"ok": False}), "abort"):
            with self.subTest(spec=str(spec)):
                page, _ = self.open_app({"state": spec}, query="?score=3&streak=1&prize=5")
                page.wait_for_function("document.querySelector('#global-score-val').textContent === '3'")
                self.assertTrue(page.is_hidden("#error-screen"))
                self.assertTrue(page.is_hidden("#ban-screen"))

    # ---- ko'rinish sifati -------------------------------------------------------------------
    def test_contrast_light_and_dark(self):
        for scheme in ("light", "dark"):
            init = f"window.Telegram.WebApp.colorScheme = '{scheme}';"
            with self.subTest(scheme=scheme, screen="ban"):
                page, _ = self.open_banned(init_script=init)
                for sel in ("#ban-title", "#ban-until", "#ban-reason", "#ban-contact"):
                    self.assertGreaterEqual(page.evaluate(CONTRAST_JS, sel), 4.5, sel)
            with self.subTest(scheme=scheme, screen="error"):
                page, _ = self.open_app({"state": SERVER_ERROR}, init_script=init)
                page.wait_for_selector("#error-screen:not([hidden])")
                for sel in ("#error-title", "#error-screen .block-line", "#error-screen .block-hint", "#error-retry"):
                    self.assertGreaterEqual(page.evaluate(CONTRAST_JS, sel), 4.5, sel)

    def test_icon_circles_are_readable(self):
        """Ikonka doirasi: ikonka rangi fon rangidan yetarli ajraladi (>= 3:1, grafik element)."""
        for scheme in ("light", "dark"):
            page, _ = self.open_banned(init_script=f"window.Telegram.WebApp.colorScheme = '{scheme}';")
            ratio = page.evaluate("""() => { const parse = (c) => c.match(/[\\d.]+/g).map(Number);
                const lum = ([r, g, b]) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
                                              return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
                const el = document.querySelector('#ban-screen .block-icon'); const cs = getComputedStyle(el);
                const a = lum(parse(cs.color)), b = lum(parse(cs.backgroundColor));
                return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05); }""")
            self.assertGreaterEqual(ratio, 3.0, scheme)

    def test_fits_a_360px_phone_even_with_a_long_reason(self):
        long_reason = "Juda uzun sabab " * 12
        for spec in ((403, {**BANNED[1], "reason": long_reason[:200]}), None):
            with self.subTest(screen="ban" if spec else "error"):
                page, _ = self.open_app({"state": spec or SERVER_ERROR})
                page.set_viewport_size({"width": 360, "height": 640})
                page.wait_for_selector("#ban-screen:not([hidden])" if spec else "#error-screen:not([hidden])")
                geo = page.evaluate("""() => { const s = [...document.querySelectorAll('.block-screen')].find((e) => !e.hidden);
                    const over = [...s.querySelectorAll('.block-card *')].filter((e) => e.scrollWidth > e.clientWidth + 1).length;
                    return { docOver: document.documentElement.scrollWidth - document.documentElement.clientWidth, over: over,
                             cardW: s.querySelector('.block-card').getBoundingClientRect().width }; }""")
                self.assertLessEqual(geo["docOver"], 0)
                self.assertEqual(geo["over"], 0)
                self.assertLessEqual(geo["cardW"], 360)

    def test_retry_button_is_a_comfortable_tap_target(self):
        page, _ = self.open_app({"state": SERVER_ERROR})
        page.wait_for_selector("#error-screen:not([hidden])")
        box = page.locator("#error-retry").bounding_box()
        self.assertGreaterEqual(box["height"], 43.9)
        self.assertGreaterEqual(box["width"], 43.9)


class BanScreenStaticTest(unittest.TestCase):
    def test_new_functions_never_use_innerhtml(self):
        js = read("app", "app.js")
        for name in ("lockApp", "showBanScreen", "showErrorScreen", "inspectApiBlock", "formatBanUntil"):
            start = js.index(f"function {name}(")
            end = js.index("\n}\n", start)
            self.assertNotIn("innerHTML", js[start:end], name)

    def test_markup_has_no_inline_style_or_handlers_and_uses_sprite_icons(self):
        html = read("app", "index.html")
        for screen_id in ("ban-screen", "error-screen"):
            start = html.index(f'id="{screen_id}"')
            block = html[start: html.index("</section>", start)]
            self.assertNotRegex(block, r"\sstyle=")
            self.assertNotRegex(block, r"\son[a-z]+=")
            self.assertIn("<use href=\"#i-", block)
            self.assertNotRegex(block, "[\U0001F300-\U0001FAFF☀-➿]")           # emoji yo'q
        self.assertIn('id="i-ban"', html)
        self.assertIn('id="i-alert-triangle"', html)

    def test_error_screen_text_never_mentions_a_ban(self):
        html = read("app", "index.html")
        start = html.index('id="error-screen"')
        block = html[start: html.index("</section>", start)].lower()
        for word in ("ban", "blok", "chetlash"):
            self.assertNotIn(word, block)

    def test_screens_are_above_everything(self):
        css = read("app", "style.css")
        z = int(re.search(r"\.block-screen \{[^}]*z-index:\s*(\d+)", css).group(1))
        for m in re.finditer(r"z-index:\s*(\d+)", css):
            self.assertLessEqual(int(m.group(1)), z)


if __name__ == "__main__":
    unittest.main()
