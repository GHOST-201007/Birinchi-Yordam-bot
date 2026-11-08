"""
test_miniapp_bonus_redesign_e2e.py — redesign 4.4-J: Kunlik bonus.
Bottom sheet, 7 kunlik dumaloq belgilar, MainButton "Bonusni olish", qattiq ranglar -> tokenlar,
suzib turgan tugma tuzatilgan. /api/bonus/claim mantig'i test_miniapp_bonus_e2e.py da tekshiriladi.
"""
import os
import re
import unittest

from tests.e2e_base import CONTRAST_JS, STATE_OK, MiniAppE2EBase

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = {**STATE_OK, "score": 7, "streak": 3, "daily_claimed": False}


class BonusStaticTest(unittest.TestCase):
    def test_no_hardcoded_dark_colors_or_inline_styles(self):
        with open(os.path.join(ROOT, "app", "index.html"), encoding="utf-8") as f:
            html = f.read()
        a = html.index('id="daily-bonus-modal"')
        block = html[a:html.index("\n    </div>\n", a)]
        for bad in ("#111827", "rgba(255,255,255", "rgba(255, 255, 255", "style=", "wheel-center-btn", "🎁"):
            self.assertNotIn(bad, block, bad)


class BonusRedesignE2ETest(MiniAppE2EBase):
    def open_bonus(self, state=None, **kw):
        page, calls = self.open_app({"state": (200, state or STATE)}, **kw)
        if kw.get("init_data") != "":                                                  # brauzerda API yo'q
            page.wait_for_function("document.querySelector('#global-score-val').textContent === '7'")
        page.emulate_media(reduced_motion="reduce")
        page.click("#btn-open-daily-bonus")
        page.wait_for_selector("#daily-bonus-modal:not(.hidden)")
        return page, calls

    def test_light_mode_sheet_uses_tokens(self):
        page, _ = self.open_bonus()
        bg = page.evaluate("getComputedStyle(document.querySelector('.bonus-sheet-inner')).backgroundColor")
        self.assertEqual(bg, "rgb(255, 255, 255)")                                     # light'da qora emas (--surface)
        box = page.locator(".bonus-sheet-inner").bounding_box()
        self.assertAlmostEqual(box["y"] + box["height"], 844, delta=1)                 # pastdan chiqadi

    def test_seven_day_markers(self):
        page, _ = self.open_bonus()
        cards = page.locator("#daily-bonus-grid .daily-bonus-card")
        self.assertEqual(cards.count(), 7)
        rewards = page.evaluate("[...document.querySelectorAll('#daily-bonus-grid .day-reward')].map(e => e.textContent)")
        self.assertEqual(rewards, ["+1", "+2", "+3", "+3", "+3", "+3", "+20"])
        for i in (0, 1):
            self.assertEqual(cards.nth(i).locator(".day-dot use").get_attribute("href"), "#i-check")   # olingan — ✓
        self.assertIn("active", cards.nth(2).get_attribute("class"))
        self.assertEqual(page.evaluate("getComputedStyle(document.querySelectorAll('#daily-bonus-grid .day-dot')[2]).borderTopColor"),
                         "rgb(10, 132, 198)")                                          # bugungi — --primary halqa
        self.assertEqual(cards.nth(6).locator(".day-dot use").get_attribute("href"), "#i-gift")
        self.assertEqual(cards.nth(2).get_attribute("aria-label"), "3-kun: 3 ball, bugun")
        self.assertEqual(cards.nth(0).get_attribute("aria-label"), "1-kun: 1 ball, olingan")

    def test_main_button_bonusni_olish_and_cleared_on_close(self):
        page, _ = self.open_bonus()
        tg = self.tg(page)
        self.assertTrue(tg["mainVisible"])
        self.assertEqual(tg["mainText"], "Bonusni olish")
        self.assertFalse(page.is_visible("#btn-claim-daily-bonus"))                   # Telegram ichida — faqat MainButton
        page.click("#daily-bonus-close")
        self.assertFalse(self.tg(page)["mainVisible"])

    def test_claimed_state_shows_status_without_main_button(self):
        page, _ = self.open_bonus(state={**STATE, "daily_claimed": True})
        self.assertFalse(self.tg(page)["mainVisible"])
        self.assertTrue(page.is_visible("#btn-claim-daily-bonus"))
        self.assertEqual(page.inner_text("#btn-claim-daily-bonus"), "Bugungi bonus olindi")

    def test_claim_button_in_flow_not_floating(self):
        page, _ = self.open_bonus(init_data="")                                         # brauzer: sahifadagi tugma
        self.assertTrue(page.is_visible("#btn-claim-daily-bonus"))
        self.assertEqual(page.evaluate("getComputedStyle(document.getElementById('btn-claim-daily-bonus')).position"), "static")
        btn = page.locator("#btn-claim-daily-bonus").bounding_box()
        note = page.locator(".bonus-note").bounding_box()
        sheet = page.locator(".bonus-sheet-inner").bounding_box()
        self.assertGreaterEqual(btn["y"], note["y"] + note["height"])                 # eslatmadan keyin, ustiga chiqmaydi
        self.assertLessEqual(btn["y"] + btn["height"], sheet["y"] + sheet["height"])
        self.assertAlmostEqual(btn["x"], note["x"], delta=1)
        self.assertAlmostEqual(btn["width"], note["width"], delta=1)

    def test_text_contrast_both_themes(self):
        for scheme in ("light", "dark"):
            with self.subTest(scheme=scheme):
                page, _ = self.open_bonus(init_data="", init_script=f"window.Telegram.WebApp.colorScheme = '{scheme}';")
                for sel in ("#daily-bonus-title", ".bonus-sheet .sheet-sub", ".bonus-score-row span", "#daily-bonus-current-score",
                            ".bonus-note span", "#btn-claim-daily-bonus"):
                    self.assertGreaterEqual(page.evaluate(CONTRAST_JS, sel), 4.5, sel)


if __name__ == "__main__":
    unittest.main()
