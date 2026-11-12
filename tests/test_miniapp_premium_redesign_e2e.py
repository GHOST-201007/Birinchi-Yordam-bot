"""
test_miniapp_premium_redesign_e2e.py — redesign 4.4-K: Premium.
Bottom sheet, crown doirada, 3 ta tanlanadigan tarif (radio), "Eng ko'p tanlanadi" — Pro (ichki plus),
✓ imkoniyatlar (AI limitlari database.py bilan mos), MainButton "★ 150 — Davom etish" -> buyPremium(plan).
To'lov oqimi (/api/invoice -> tg.openInvoice) test_miniapp_invoice_e2e.py da tekshiriladi.
"""
import os
import re
import unittest

from tests.e2e_base import CONTRAST_JS, MiniAppE2EBase

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RADIO = '#premium-modal input[name="premium-plan"][value="{}"]'


class PremiumStaticTest(unittest.TestCase):
    def test_ai_limits_match_database_defaults(self):
        with open(os.path.join(ROOT, "database.py"), encoding="utf-8") as f:
            db = f.read()
        limits = {k: re.search(rf'"{k}_AI_DAILY_LIMIT", "(\d+)"', db).group(1) for k in ("PRO", "PLUS", "ULTRA")}
        with open(os.path.join(ROOT, "app", "app.js"), encoding="utf-8") as f:
            js = f.read()
        block = js[js.index("const PREMIUM_FEATURES = {"):js.index("};", js.index("const PREMIUM_FEATURES = {"))]
        for plan, key in (("buy_pro_7", "PRO"), ("buy_plus_30", "PLUS"), ("buy_ultra_30", "ULTRA")):
            line = re.search(rf"{plan}: \[(.*)\]", block).group(1)
            self.assertIn(f"Kuniga {limits[key]} AI so'rov", line, plan)
        self.assertNotIn("100+", block)
        self.assertNotIn("Cheksiz imkoniyatlar", block)                     # limitga zid va'da (egasi tasdiqlaguncha)

    def test_no_inline_handlers(self):
        with open(os.path.join(ROOT, "app", "index.html"), encoding="utf-8") as f:
            html = f.read()
        block = html[html.index('id="premium-modal"'):html.index("<!-- Script ulanishi -->")]
        self.assertNotIn("onclick=", block)
        self.assertNotIn("👑", block)


class PremiumRedesignE2ETest(MiniAppE2EBase):
    def open_premium(self, **kw):
        page, calls = self.open_app({}, **kw)
        page.emulate_media(reduced_motion="reduce")
        page.click('nav [data-tab="tab-health"]')
        page.click("#btn-open-premium")
        page.wait_for_selector("#premium-modal:not(.hidden)")
        return page, calls

    def test_sheet_header_and_plans(self):
        page, _ = self.open_premium()
        self.assertEqual(page.inner_text("#premium-title"), "Premium")
        self.assertEqual(page.get_attribute("#premium-modal .pm-crown use", "href"), "#i-crown")
        box = page.locator("#premium-modal .pm-sheet").bounding_box()
        self.assertAlmostEqual(box["y"] + box["height"], 844, delta=1)
        names = page.evaluate("[...document.querySelectorAll('#premium-modal .plan-name')].map(e => e.childNodes[0].textContent)")
        self.assertEqual(names, ["Premium Plus", "Premium Pro", "Premium Ultra"])   # ichki pro / plus / ultra
        prices = page.evaluate("[...document.querySelectorAll('#premium-modal .plan-price')].map(e => e.textContent)")
        self.assertEqual(prices, ["★ 50", "★ 150", "★ 300"])
        self.assertEqual(page.get_attribute("#premium-modal .plan-list", "role"), "radiogroup")
        self.assertTrue(page.is_checked(RADIO.format("buy_plus_30")))                # standart — Pro (ichki plus)
        chip = page.locator("#premium-modal .plan-chip")
        self.assertEqual(chip.count(), 1)
        self.assertEqual(chip.inner_text(), "Eng ko'p tanlanadi")
        self.assertEqual(page.evaluate("document.querySelector('#premium-modal .plan-chip').closest('.plan-card').querySelector('input').value"),
                         "buy_plus_30")

    def test_selection_updates_features_and_main_button(self):
        page, _ = self.open_premium()
        tg = self.tg(page)
        self.assertTrue(tg["mainVisible"])
        self.assertEqual(tg["mainText"], "★ 150 — Davom etish")
        self.assertFalse(page.is_visible("#premium-continue"))
        feats = page.evaluate("[...document.querySelectorAll('#premium-features li')].map(e => e.textContent)")
        self.assertEqual(feats[0], "Kuniga 30 AI so'rov")
        self.assertEqual(page.locator("#premium-features .pm-check svg").count(), len(feats))
        page.click("#premium-modal .plan-card:has(input[value='buy_ultra_30'])")
        self.assertTrue(page.is_checked(RADIO.format("buy_ultra_30")))
        self.assertEqual(self.tg(page)["mainText"], "★ 300 — Davom etish")
        self.assertEqual(page.inner_text("#premium-features li:first-child"), "Kuniga 100 AI so'rov")

    def test_main_button_calls_buy_premium_with_selected_plan(self):
        page, _ = self.open_premium()
        page.evaluate("() => { window.__bought = []; window.buyPremium = (p) => window.__bought.push(p); }")
        page.click("#premium-modal .plan-card:has(input[value='buy_pro_7'])")
        page.evaluate("window.__mainCb()")
        self.assertEqual(page.evaluate("window.__bought"), ["buy_pro_7"])

    def test_keyboard_arrows_change_plan(self):
        page, _ = self.open_premium()
        page.focus(RADIO.format("buy_plus_30"))
        page.keyboard.press("ArrowDown")
        self.assertTrue(page.is_checked(RADIO.format("buy_ultra_30")))
        self.assertEqual(self.tg(page)["mainText"], "★ 300 — Davom etish")

    def test_close_clears_main_button(self):
        page, _ = self.open_premium()
        page.click("#premium-modal-close")
        page.wait_for_selector("#premium-modal.hidden", state="attached")
        self.assertFalse(self.tg(page)["mainVisible"])
        self.assertFalse(self.tg(page)["backVisible"])

    def test_browser_fallback_and_contrast(self):
        for scheme in ("light", "dark"):
            with self.subTest(scheme=scheme):
                page, _ = self.open_premium(init_data="", init_script=f"window.Telegram.WebApp.colorScheme = '{scheme}';")
                self.assertTrue(page.is_visible("#premium-continue"))
                self.assertEqual(page.inner_text("#premium-continue"), "★ 150 — Davom etish")
                for sel in ("#premium-title", "#premium-modal .pm-subtitle", "#premium-modal .plan-name",
                            "#premium-modal .plan-days", "#premium-modal .plan-price", "#premium-modal .plan-chip",
                            "#premium-features li span:last-child", "#premium-continue"):
                    self.assertGreaterEqual(page.evaluate(CONTRAST_JS, sel), 4.5, sel)
                page.evaluate("() => { window.__bought = []; window.buyPremium = (p) => window.__bought.push(p); }")
                page.click("#premium-continue")
                self.assertEqual(page.evaluate("window.__bought"), ["buy_plus_30"])


if __name__ == "__main__":
    unittest.main()
