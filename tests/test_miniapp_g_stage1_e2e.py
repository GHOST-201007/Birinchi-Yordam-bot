"""
test_miniapp_g_stage1_e2e.py — G Stage 1 (docs/MINI_APP_G_TASK.md): tokenlar, Nunito (o'zimizda), 4 tabli nav (AI).
"""
import os
import re
import unittest

from tests.e2e_base import MiniAppE2EBase

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIGHT = {"--bg": "#EEF8F5", "--surface": "#FFFFFF", "--text": "#0F2A2E", "--text-2": "#4F6B6E", "--primary": "#0E7C72",
         "--on-primary": "#FFFFFF", "--danger": "#B4231B", "--warning": "#9A5700", "--body-fill": "#CFEAE4"}
DARK = {"--bg": "#0C1517", "--surface": "#152225", "--text": "#E6F2F0", "--text-2": "#8FA9A9", "--primary": "#3DC2B3",
        "--on-primary": "#06211E", "--danger": "#FF8A8A", "--warning": "#F5B544", "--body-fill": "#1F3A3B"}


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class TokensStaticTest(unittest.TestCase):
    def test_single_root_and_dark_blocks_no_old_tokens(self):
        css = read("app/style.css")
        self.assertEqual(len(re.findall(r"^:root\b", css, re.M)), 1)
        self.assertEqual(len(re.findall(r"^body\.dark-mode\s*\{", css, re.M)), 1)
        for old in ("--primary-strong", "--danger-strong", "var(--separator)", "var(--teal", "body.tg-light"):
            self.assertNotIn(old, css, old)
        self.assertNotIn("--primary-strong", read("app/app.js"))

    def test_nunito_is_local_latin_woff2(self):
        css = read("app/style.css")
        self.assertIn('src: url("fonts/nunito-latin.woff2") format("woff2")', css)
        self.assertIn("font-display: swap", css)
        self.assertNotRegex(css, r"fonts\.(googleapis|gstatic)\.com")
        path = os.path.join(ROOT, "app", "fonts", "nunito-latin.woff2")
        with open(path, "rb") as f:
            self.assertEqual(f.read(4), b"wOF2")
        self.assertTrue(os.path.exists(os.path.join(ROOT, "app", "fonts", "OFL.txt")))      # litsenziya


class Stage1E2ETest(MiniAppE2EBase):
    def tokens(self, page):
        return page.evaluate("""(names) => { const cs = getComputedStyle(document.body);
            return Object.fromEntries(names.map(n => [n, cs.getPropertyValue(n).trim().toUpperCase()])); }""", list(LIGHT))

    def test_tokens_light_and_dark(self):
        for scheme, expected in (("light", LIGHT), ("dark", DARK)):
            with self.subTest(scheme=scheme):
                page, _ = self.open_app({}, init_script=f"window.Telegram.WebApp.colorScheme = '{scheme}';")
                self.assertEqual(self.tokens(page), {k: v.upper() for k, v in expected.items()})

    def test_nunito_font_loads_from_own_server(self):
        page, _ = self.open_app({})
        page.wait_for_function("document.fonts.status === 'loaded'")
        self.assertTrue(page.evaluate("document.fonts.check('800 16px Nunito')"))
        self.assertTrue(page.evaluate("getComputedStyle(document.body).fontFamily.startsWith('Nunito')"))

    def test_nav_four_tabs_with_ai(self):
        page, _ = self.open_app({})
        tabs = page.evaluate("[...document.querySelectorAll('nav .nav-btn')].map(b => [b.dataset.tab, b.innerText.trim(), b.querySelector('use').getAttribute('href')])")
        self.assertEqual(tabs, [["tab-first-aid", "Yordam", "#i-first-aid"], ["tab-diseases", "Kasalliklar", "#i-book"],
                                ["tab-health", "Sog'liq", "#i-heart-pulse"], ["tab-ai", "AI", "#i-sparkles"]])
        nav = page.locator(".app-nav").bounding_box()
        self.assertAlmostEqual(nav["height"], 64, delta=1)
        active = page.evaluate("(() => { const s = getComputedStyle(document.querySelector('.nav-btn.active')); return [s.color, s.fontWeight, s.fontSize]; })()")
        self.assertEqual(active, ["rgb(14, 124, 114)", "800", "11px"])
        idle = page.evaluate("(() => { const s = getComputedStyle(document.querySelector('.nav-btn:not(.active)')); return [s.color, s.fontWeight]; })()")
        self.assertEqual(idle, ["rgb(79, 107, 110)", "700"])
        self.assertEqual(page.evaluate("getComputedStyle(document.querySelector('.nav-btn .icon')).width"), "24px")

    def test_ai_tab_placeholder(self):
        page, _ = self.open_app({})
        page.click('nav [data-tab="tab-ai"]')
        page.wait_for_selector("#tab-ai.active")
        self.assertIn("Tez orada", page.inner_text("#tab-ai"))
        self.assertEqual(page.get_attribute('nav [data-tab="tab-ai"]', "aria-current"), "page")


if __name__ == "__main__":
    unittest.main()
