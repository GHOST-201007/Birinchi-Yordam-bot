"""
test_miniapp_history_e2e.py — redesign 4.4-G: Tarix.
Grafik — bitta rang (--primary), to'r chiziqlari --separator, nuqtalarsiz (faqat oxirgisi), mavzu o'zgarsa qayta chiziladi.
Log — inset grouped: sana chapda, qiymat o'ngda (tabular). Saqlash formati o'zgarmagan. Asos: tests/e2e_base.py
"""
import json
import re
import unittest

from tests.e2e_base import MiniAppE2EBase

EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⬀-⯿]")
BMI = [{"date": f"{d}.11.2026", "bmi": b, "weight": 70, "height": 175, "status": "x"}
       for d, b in ((1, "26.1"), (3, "25.8"), (5, "24.9"), (8, "17.9"))]
# Kanvasda berilgan rangga yaqin piksel bormi (chiziq markazi aniq rangda chiziladi)
HAS_COLOR_JS = """([id, r, g, b]) => { const c = document.getElementById(id); const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
    for (let i = 0; i < d.length; i += 4) if (Math.abs(d[i] - r) < 3 && Math.abs(d[i+1] - g) < 3 && Math.abs(d[i+2] - b) < 3 && d[i+3] > 250) return true;
    return false; }"""


class HistoryE2ETest(MiniAppE2EBase):
    def open_history(self, bmi=None, water=None, **kw):
        seed = ""
        if bmi is not None:
            seed += f"localStorage.setItem('history_bmi', {json.dumps(json.dumps(bmi))});"
        if water is not None:
            seed += f"localStorage.setItem('history_water', {json.dumps(json.dumps(water))});"
        page, _ = self.open_app({}, init_script=seed + kw.pop("init_script", ""), **kw)
        page.click('nav [data-tab="tab-health"]')
        page.click('#tab-health [data-show-tab="tab-history"]')
        return page

    def test_no_emoji_no_inline_handlers(self):
        page = self.open_history()
        self.assertIsNone(EMOJI.search(page.inner_text("#tab-history")))
        self.assertEqual(page.evaluate("document.querySelectorAll('#tab-history [onclick], #tab-history [style]').length"), 0)
        self.assertEqual(page.get_attribute("#tab-history .screen-title use", "href"), "#i-chart")

    def test_empty_state(self):
        page = self.open_history()
        self.assertTrue(page.is_visible("#bmi-chart-empty"))
        self.assertFalse(page.is_visible("#bmi-chart"))
        self.assertFalse(page.is_visible("#bmi-history-log"))
        self.assertFalse(page.is_visible("#btn-clear-bmi-history"))

    def test_single_entry_explains_chart_needs_two(self):
        page = self.open_history(bmi=BMI[:1])
        self.assertIn("ikkinchi natijadan", page.inner_text("#bmi-chart-empty"))
        self.assertEqual(page.locator("#bmi-history-log .history-row").count(), 1)

    def test_log_date_left_value_right_with_chip(self):
        page = self.open_history(bmi=BMI)
        rows = page.locator("#bmi-history-log .history-row")
        self.assertEqual(rows.count(), 4)
        first = rows.first
        self.assertEqual(first.locator(".h-date").inner_text(), "8.11.2026")                 # eng yangisi tepada
        self.assertEqual(first.locator(".h-val").inner_text(), "BMI 17.9")
        self.assertIn("tabular", first.locator(".h-val").get_attribute("class"))
        self.assertEqual(first.locator(".chip").inner_text(), "Kam")
        self.assertIn("chip--warning", first.locator(".chip").get_attribute("class"))
        d, v, row = first.locator(".h-date").bounding_box(), first.locator(".h-val").bounding_box(), first.bounding_box()
        self.assertLess(d["x"], row["x"] + row["width"] / 3)
        self.assertGreater(v["x"], row["x"] + row["width"] / 2)
        chips = page.evaluate("[...document.querySelectorAll('#bmi-history-log .chip')].map(c => c.textContent)")
        self.assertEqual(chips, ["Kam", "Normal", "Yuqori", "Yuqori"])

    def test_chart_drawn_when_opened_single_primary_color(self):
        page = self.open_history(bmi=BMI)
        self.assertTrue(page.is_visible("#bmi-chart"))
        self.assertGreater(page.evaluate("document.getElementById('bmi-chart').width"), 100)  # yashirin bo'limda 0 emas
        self.assertTrue(page.evaluate(HAS_COLOR_JS, ["bmi-chart", 14, 124, 114]))            # --primary (light)
        self.assertFalse(page.evaluate(HAS_COLOR_JS, ["bmi-chart", 0, 122, 255]))            # eski #007aff yo'q
        self.assertEqual(page.get_attribute("#bmi-chart", "aria-label"), "BMI grafigi: 4 ta natija, oxirgisi 17.9")

    def test_chart_redrawn_on_theme_change(self):
        page = self.open_history(bmi=BMI)
        page.evaluate("window.Telegram.WebApp.colorScheme = 'dark'; window.__tgEvents.themeChanged()")
        self.assertTrue(page.evaluate("document.body.classList.contains('dark-mode')"))
        self.assertTrue(page.evaluate(HAS_COLOR_JS, ["bmi-chart", 61, 194, 179]))             # --primary (dark)

    def test_switch_to_water_and_clear(self):
        page = self.open_history(bmi=BMI, water=[{"date": "2.11.2026", "liters": "2.1", "weight": 70},
                                                 {"date": "4.11.2026", "liters": "2.4", "weight": 80}])
        page.click('[data-history="water"]')
        self.assertEqual(page.get_attribute('[data-history="water"]', "aria-selected"), "true")
        self.assertTrue(page.is_visible("#water-chart"))
        self.assertGreater(page.evaluate("document.getElementById('water-chart').width"), 100)
        self.assertEqual(page.locator("#water-history-log .h-val").first.inner_text(), "2.4 L")
        page.click("#btn-clear-water-history")
        self.assertIsNone(page.evaluate("SafeStorage.getItem('history_water')"))
        self.assertTrue(page.is_visible("#water-chart-empty"))
        self.assertEqual(page.evaluate("SafeStorage.getItem('history_bmi') !== null"), True)   # BMI tarixi qoladi

    def test_stored_values_rendered_as_text(self):
        page = self.open_history(bmi=[{"date": "<img src=x onerror=window.__x=1>", "bmi": "22.0"}])
        self.assertEqual(page.locator("#bmi-history-log img").count(), 0)
        self.assertIsNone(page.evaluate("window.__x"))

    def test_new_bmi_calculation_appears_in_history(self):
        page = self.open_history()
        page.click('#tab-history [data-show-tab="tab-health"]')
        page.fill("#bmi-weight", "70")
        page.fill("#bmi-height", "175")
        page.evaluate("window.__mainCb()")
        page.click('#tab-health [data-show-tab="tab-history"]')
        self.assertEqual(page.locator("#bmi-history-log .h-val").first.inner_text(), "BMI 22.9")


if __name__ == "__main__":
    unittest.main()
