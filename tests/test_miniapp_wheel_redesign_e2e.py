"""
test_miniapp_wheel_redesign_e2e.py — redesign 4.4-I: Omad barabani ("klinik" variant).
Bottom sheet (~85%), LED/neon/"KUNLIK BONUS" yo'q, 5 segment (server bilan bir xil), 4s aylanish,
confetti faqat SUPER'da, MainButton "Mukofotni olish", katta tabular taymer.
api()/getAppState/claim*/recover* mantig'i test_miniapp_wheel_e2e.py va late_response testlarida tekshiriladi.
"""
import os
import re
import unittest

from tests.e2e_base import CLAIM_OK, CONTRAST_JS, STATE_OK, MiniAppE2EBase

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⬀-⯿]")


def _lum(hex_color):
    rgb = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    f = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * f[0] + 0.7152 * f[1] + 0.0722 * f[2]


def _ratio(a, b):
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


class WheelStaticTest(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(ROOT, "app", "app.js"), encoding="utf-8") as f:
            self.js = f.read()

    def test_segments_match_server_values_and_order(self):
        block = self.js[self.js.index("const segments = ["): self.js.index("];", self.js.index("const segments = ["))]
        self.assertEqual([int(x) for x in re.findall(r"points: (\d+)", block)], [1, 3, 5, 10, 0])
        with open(os.path.join(ROOT, "database.py"), encoding="utf-8") as f:
            db = f.read()
        self.assertIn("Frontend segments: 1, 3, 5, 10, 0 (SUPER)", db)
        server = [int(x) for x in re.findall(r"prize = (\d+)", db[db.index("# Generate new prize"):db.index("# Jami: 1,3,5,10,SUPER")])]
        self.assertEqual(sorted(server), sorted([1, 3, 5, 10, 0]))

    def test_segment_text_contrast(self):
        block = self.js[self.js.index("function segmentColors(tone)"):self.js.index("function drawWheel()")]
        pairs = re.findall(r"\['(#[0-9A-Fa-f]{6})', '(#[0-9A-Fa-f]{6})'\]", block)
        self.assertEqual(len(pairs), 10)                                     # 5 ton x 2 mavzu
        for bg, fg in pairs:
            self.assertGreaterEqual(_ratio(bg, fg), 4.5, (bg, fg))

    def test_no_led_neon_badge(self):
        with open(os.path.join(ROOT, "app", "index.html"), encoding="utf-8") as f:
            html = f.read()
        for bad in ("wheel-led", "KUNLIK BONUS", "badge-dot", "wheel-pointer-gem"):
            self.assertNotIn(bad, html)
        self.assertNotIn("generateLedLights", self.js)


class WheelRedesignE2ETest(MiniAppE2EBase):
    def open_ready(self, state=None, **kw):
        page, calls = self.open_app({"state": (200, state or STATE_OK), "spin/claim": (200, CLAIM_OK)}, **kw)
        self.open_wheel(page)
        page.wait_for_function("!document.querySelector('#btn-spin-wheel').disabled")
        return page, calls

    def test_bottom_sheet_85_percent(self):
        page, _ = self.open_app({"state": (200, STATE_OK)})
        page.emulate_media(reduced_motion="reduce")                                   # kirish animatsiyasisiz o'lchash
        self.open_wheel(page)
        box = page.locator("#wheel-modal .wheel-modal-inner").bounding_box()
        self.assertAlmostEqual(box["height"], 844 * 0.85, delta=2)
        self.assertAlmostEqual(box["y"] + box["height"], 844, delta=1)
        self.assertIsNone(EMOJI.search(page.inner_text("#wheel-modal")))
        self.assertEqual(page.get_attribute("#btn-spin-wheel", "aria-label"), "Barabanni aylantirish")

    def test_spin_4s_ease_and_main_button_claims(self):
        page, calls = self.open_ready()
        page.click("#btn-spin-wheel")
        self.assertIn("4000ms", page.evaluate("document.getElementById('wheel-canvas').style.transition"))
        page.clock.fast_forward(3900)
        self.assertEqual(page.locator("#btn-confirm-spin").count(), 0)              # animatsiya tugamagan
        page.clock.fast_forward(300)
        page.wait_for_selector("#btn-confirm-spin", state="attached")
        tg = self.tg(page)
        self.assertTrue(tg["mainVisible"])
        self.assertEqual(tg["mainText"], "Mukofotni olish")
        self.assertFalse(page.is_visible("#btn-confirm-spin"))
        self.assertIn("result-icon", page.inner_html("#wheel-result-msg"))
        self.assertEqual(page.locator("#wheel-result-msg .result-icon svg").count(), 1)
        page.evaluate("window.__mainCb()")
        self.wait_for_call(calls, "spin/claim")
        page.wait_for_selector("#wheel-result-msg .result-title:has-text('+5 ball yutdingiz!')")
        self.assertFalse(self.tg(page)["mainVisible"])                              # kartada tugma yo'q — MainButton ham yo'q

    def test_reduced_motion_short_spin(self):
        page, _ = self.open_ready()
        page.emulate_media(reduced_motion="reduce")
        page.click("#btn-spin-wheel")
        self.assertIn("600ms", page.evaluate("document.getElementById('wheel-canvas').style.transition"))
        page.clock.fast_forward(800)
        page.wait_for_selector("#btn-confirm-spin", state="attached")

    def test_confetti_only_for_super(self):
        for prize, expected in ((5, 0), (0, 1)):
            with self.subTest(prize=prize):
                page, _ = self.open_ready(state={**STATE_OK, "prize": prize})
                page.evaluate("() => { window.__confetti = 0; window.fireConfetti = () => { window.__confetti++; }; }")
                self.spin_and_finish(page)
                self.assertEqual(page.evaluate("window.__confetti"), expected)

    def test_main_button_cleared_when_sheet_closed(self):
        page, _ = self.open_ready()
        self.spin_and_finish(page)
        self.assertTrue(self.tg(page)["mainVisible"])
        page.click("#wheel-modal-close")
        page.wait_for_function("document.getElementById('wheel-modal').style.display === 'none'")
        self.assertFalse(self.tg(page)["mainVisible"])

    def test_waiting_state_big_tabular_timer(self):
        for scheme in ("light", "dark"):
            with self.subTest(scheme=scheme):
                page, _ = self.open_app({"state": (200, {**STATE_OK, "prize": None, "cooldown_seconds": 51725})},
                                        init_script=f"window.Telegram.WebApp.colorScheme = '{scheme}';")
                self.open_wheel(page)
                page.wait_for_selector("#wheel-countdown-timer")
                self.assertRegex(page.inner_text("#wheel-countdown-timer"), r"^14:22:0\d$")
                timer = page.locator("#wheel-countdown-timer")
                self.assertIn("tabular", timer.get_attribute("class"))
                self.assertGreaterEqual(page.evaluate("parseFloat(getComputedStyle(document.getElementById('wheel-countdown-timer')).fontSize)"), 40)
                self.assertIsNone(timer.get_attribute("style"))
                for sel in ("#wheel-countdown-timer", "#wheel-result-msg .result-title", "#wheel-result-msg .result-desc",
                            "#btn-spin-wheel .wheel-center-text"):
                    self.assertGreaterEqual(page.evaluate(CONTRAST_JS, sel), 4.5, sel)
                self.assertFalse(self.tg(page)["mainVisible"])                     # kutishda asosiy amal yo'q

    def test_browser_fallback_card_button_visible(self):
        page, _ = self.open_app({}, query="?prize=3", init_data="")
        self.open_wheel(page)
        page.wait_for_function("!document.querySelector('#btn-spin-wheel').disabled")
        self.spin_and_finish(page)
        self.assertTrue(page.is_visible("#btn-confirm-spin"))
        self.assertEqual(page.inner_text("#btn-confirm-spin"), "Mukofotni olish")
        self.assertGreaterEqual(page.evaluate(CONTRAST_JS, "#btn-confirm-spin"), 4.5)


if __name__ == "__main__":
    unittest.main()
