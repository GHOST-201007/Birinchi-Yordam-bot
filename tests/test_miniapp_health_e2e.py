"""
test_miniapp_health_e2e.py — redesign 4.4-E: Sog'liq (kalkulyatorlar).
SVG ikonkalar (emoji yo'q), BMI·Suv·Kaloriya segmented, 52px birlikli maydonlar,
"Hisoblash" — Telegram ichida MainButton (input to'g'ri bo'lsagina faol), tashqarida sahifadagi tugma.
Asos: tests/e2e_base.py
"""
import re
import unittest

from tests.e2e_base import CONTRAST_JS, MiniAppE2EBase

EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⬀-⯿]")


class HealthE2ETest(MiniAppE2EBase):
    def open_health(self, **kw):
        page, _ = self.open_app({}, **kw)
        page.click('nav [data-tab="tab-health"]')
        return page

    def test_title_and_switch_use_svg_icons_not_emoji(self):
        page = self.open_health()
        self.assertEqual(page.get_attribute("#tab-health .screen-title use", "href"), "#i-heart-pulse")
        icons = page.evaluate("[...document.querySelectorAll('[data-calc] use')].map(u => u.getAttribute('href'))")
        self.assertEqual(icons, ["#i-scale", "#i-droplet", "#i-flame"])
        text = page.inner_text("#tab-health")
        self.assertIsNone(EMOJI.search(text), text)

    def test_inputs_are_52px_with_unit_inside(self):
        page = self.open_health()
        box = page.locator("#bmi-weight").bounding_box()
        self.assertEqual(round(box["height"]), 52)
        unit = page.locator("#calc-bmi-section .input-wrap .input-unit").first
        self.assertEqual(unit.inner_text(), "kg")
        ub = unit.bounding_box()
        self.assertGreater(ub["x"], box["x"])
        self.assertLess(ub["x"] + ub["width"], box["x"] + box["width"])            # birlik maydon ichida

    def test_main_button_active_only_when_input_valid(self):
        page = self.open_health()
        tg = self.tg(page)
        self.assertTrue(tg["mainVisible"])
        self.assertEqual(tg["mainText"], "Hisoblash")
        self.assertFalse(tg["mainActive"])
        self.assertFalse(page.is_visible("#btn-calculate-bmi"))                     # Telegram ichida — faqat MainButton
        page.fill("#bmi-weight", "78")
        self.assertFalse(self.tg(page)["mainActive"])
        page.fill("#bmi-height", "175")
        self.assertTrue(self.tg(page)["mainActive"])
        page.fill("#bmi-height", "")
        self.assertFalse(self.tg(page)["mainActive"])

    def test_main_button_calculates_bmi_with_status_chip(self):
        page = self.open_health()
        page.fill("#bmi-weight", "78")
        page.fill("#bmi-height", "175")
        page.evaluate("window.__mainCb()")
        self.assertTrue(page.is_visible("#bmi-result-card"))
        self.assertEqual(page.inner_text("#bmi-number"), "25.5")
        self.assertEqual(page.inner_text("#bmi-status"), "Ortiqcha vazn")
        self.assertIn("chip--warning", page.get_attribute("#bmi-status", "class"))
        self.assertEqual(page.evaluate("document.getElementById('bmi-gauge-pointer').style.left"), "65%")
        self.assertEqual(page.inner_text("#bmi-ideal-range"), "56.7 - 76.3 kg")
        hist = page.evaluate("JSON.parse(SafeStorage.getItem('history_bmi'))")
        self.assertEqual(hist[-1]["status"], "Ortiqcha vazn")                       # tarix formati o'zgarmagan

    def test_status_chip_colors(self):
        page = self.open_health()
        for w, status, cls in (("50", "Kam vazn", "chip--warning"), ("70", "Normal vazn", "chip--teal"),
                               ("100", "Semizlik", "chip--danger")):
            with self.subTest(status=status):
                page.fill("#bmi-weight", w)
                page.fill("#bmi-height", "175")
                page.evaluate("window.__mainCb()")
                self.assertEqual(page.inner_text("#bmi-status"), status)
                self.assertIn(cls, page.get_attribute("#bmi-status", "class"))

    def test_switch_to_water_and_calorie(self):
        page = self.open_health()
        page.click('[data-calc="water"]')
        self.assertEqual(page.get_attribute('[data-calc="water"]', "aria-selected"), "true")
        self.assertTrue(page.is_visible("#water-weight"))
        self.assertFalse(page.is_visible("#bmi-weight"))
        self.assertFalse(self.tg(page)["mainActive"])
        page.fill("#water-weight", "70")
        self.assertTrue(self.tg(page)["mainActive"])
        page.evaluate("window.__mainCb()")
        self.assertEqual(page.inner_text("#water-value"), "2.1 Litr")
        self.assertEqual(page.inner_text("#water-sport"), "2.6 L")

        page.click('[data-calc="calorie"]')
        self.assertFalse(page.is_visible("#water-result-card"))                    # boshqa natija yashirinadi
        page.fill("#calorie-weight", "70")
        page.fill("#calorie-height", "175")
        page.fill("#calorie-age", "25")
        page.evaluate("window.__mainCb()")
        self.assertEqual(page.inner_text("#calorie-value"), "2009 kkal")           # Mifflin-St Jeor, o'zgarmagan

    def test_main_button_only_on_calculator_screen(self):
        page = self.open_health()
        self.assertTrue(self.tg(page)["mainVisible"])
        page.click('[data-show-tab="tab-history"]')
        self.assertFalse(self.tg(page)["mainVisible"])
        page.click('#tab-history [data-show-tab="tab-health"]')
        self.assertTrue(self.tg(page)["mainVisible"])
        page.click('nav [data-tab="tab-diseases"]')
        self.assertFalse(self.tg(page)["mainVisible"])
        self.assertIsNone(page.evaluate("window.__mainCb"))

    def test_bottom_padding_while_main_button_visible(self):
        page = self.open_health()
        self.assertTrue(page.evaluate("document.body.classList.contains('tg-main-on')"))
        pad = page.evaluate("parseFloat(getComputedStyle(document.querySelector('.app-content')).paddingBottom)")
        self.assertGreaterEqual(pad, 90)
        page.click('nav [data-tab="tab-first-aid"]')
        self.assertFalse(page.evaluate("document.body.classList.contains('tg-main-on')"))

    def test_browser_fallback_button_outside_telegram(self):
        page = self.open_health(init_data="")
        self.assertFalse(self.tg(page)["mainVisible"])
        btn = page.locator("#btn-calculate-bmi")
        self.assertTrue(btn.is_visible())
        self.assertTrue(btn.is_disabled())
        page.fill("#bmi-weight", "70")
        page.fill("#bmi-height", "175")
        self.assertTrue(btn.is_enabled())
        btn.click()
        self.assertEqual(page.inner_text("#bmi-status"), "Normal vazn")
        page.click('[data-calc="water"]')
        self.assertTrue(page.is_visible("#btn-calculate-water"))
        page.fill("#water-weight", "70")
        page.click("#btn-calculate-water")
        self.assertEqual(page.inner_text("#water-value"), "2.1 Litr")

    def test_fallback_button_contrast_aa_in_both_themes(self):
        for scheme in ("light", "dark"):
            with self.subTest(scheme=scheme):
                page = self.open_health(init_data="",
                                        init_script=f"window.Telegram.WebApp.colorScheme = '{scheme}';")
                page.fill("#bmi-weight", "70")
                page.fill("#bmi-height", "175")
                self.assertGreaterEqual(page.evaluate(CONTRAST_JS, "#btn-calculate-bmi"), 4.5)
                self.assertGreaterEqual(page.evaluate(CONTRAST_JS, '[data-calc="bmi"]'), 4.5)


if __name__ == "__main__":
    unittest.main()
